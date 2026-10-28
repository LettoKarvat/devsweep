"""Read-only scanning and validation. No filesystem deletion lives here."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import stat
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__

CACHE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_NAMES = {".git", "$recycle.bin", "system volume information", "recovery"}
MANIFESTS = {"package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile", "uv.lock"}


def canonical(path: Path | str) -> Path:
    return Path(os.path.abspath(path)).resolve(strict=True)


def within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def kind_of(path: Path) -> str | None:
    if path.name == "node_modules":
        return "Node.js"
    if (path / "pyvenv.cfg").is_file():
        return "Python venv"
    if path.name in CACHE_NAMES:
        return "Cache Python"
    return None


def protected_paths() -> tuple[Path, ...]:
    values = [sys.base_prefix, sys.prefix]
    values.extend(os.environ.get(key) for key in ("WINDIR", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"))
    for key, suffix in (("APPDATA", "npm"), ("LOCALAPPDATA", "Programs")):
        if os.environ.get(key):
            values.append(str(Path(os.environ[key]) / suffix))
    paths = []
    for value in values:
        if value:
            try:
                paths.append(canonical(value))
            except OSError:
                pass
    return tuple(paths)


def _cancelled(cancel: threading.Event | None) -> None:
    if cancel and cancel.is_set():
        raise InterruptedError("Operação interrompida.")


@dataclass(frozen=True)
class Snapshot:
    size: int
    files: int
    newest_ns: int
    fingerprint: str
    complete: bool
    has_links: bool


def measure_tree(root: Path, cancel: threading.Event | None = None) -> Snapshot:
    """Measure logical bytes, without following any link or reparse point."""
    size = files = newest = 0
    complete, links = True, False
    # XOR of per-entry SHA-256 digests is independent of scandir order.
    checksum = 0
    stack = [root]
    while stack:
        _cancelled(cancel)
        path = stack.pop()
        try:
            info = path.lstat()
            if is_link(path):
                links = True
                continue
            newest = max(newest, info.st_mtime_ns)
            relative = str(path.relative_to(root))
            record = f"{relative}|{info.st_mode}|{info.st_size}|{info.st_mtime_ns}|{info.st_ino}"
            checksum ^= int.from_bytes(hashlib.sha256(record.encode("utf-8", "surrogatepass")).digest(), "big")
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as entries:
                    stack.extend(Path(entry.path) for entry in entries)
            elif stat.S_ISREG(info.st_mode):
                size += info.st_size
                files += 1
            else:
                complete = False
        except OSError:
            complete = False
    return Snapshot(size, files, newest, f"{checksum:064x}", complete, links)


def find_project(path: Path, scope: Path) -> Path:
    current = path.parent
    for _ in range(12):
        if not within(current, scope):
            break
        try:
            if any((current / name).is_file() for name in MANIFESTS):
                return current
        except OSError:
            pass
        if current == scope or current == current.parent:
            break
        current = current.parent
    return path.parent


def project_activity(project: Path, cancel: threading.Event | None = None) -> tuple[int, bool]:
    """Inspect project source, excluding dependencies/caches. Bound expensive walks."""
    newest, count, complete = 0, 0, True
    stack = [project]
    while stack:
        _cancelled(cancel)
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    _cancelled(cancel)
                    count += 1
                    if count > 20_000:
                        return newest, False
                    path = Path(entry.path)
                    if is_link(path):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.lower() in SKIP_NAMES or kind_of(path):
                            continue
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        newest = max(newest, entry.stat(follow_symlinks=False).st_mtime_ns)
        except OSError:
            complete = False
    return newest, complete


@dataclass(frozen=True)
class Candidate:
    path: Path
    scope: Path
    project: Path
    kind: str
    snapshot: Snapshot
    project_newest_ns: int
    identity: tuple[int, int]
    blocked: str = ""

    @property
    def newest_ns(self) -> int:
        return max(self.snapshot.newest_ns, self.project_newest_ns)

    def age_days(self, now: float | None = None) -> int:
        timestamp = time.time() if now is None else now
        return max(0, int((timestamp - self.newest_ns / 1_000_000_000) / 86400))


@dataclass(frozen=True)
class ScanOptions:
    node: bool = True
    venv: bool = True
    caches: bool = True


@dataclass
class ScanResult:
    candidates: list[Candidate]
    visited: int = 0
    errors: int = 0
    skipped: int = 0
    cancelled: bool = False


def normalize_roots(roots: list[Path | str]) -> list[Path]:
    normalized: list[Path] = []
    for value in roots:
        original = Path(os.path.abspath(value))
        current = original
        while True:
            if is_link(current):
                raise ValueError(f"A raiz não pode atravessar um link ou ponto de redirecionamento: {current}")
            if current == current.parent:
                break
            current = current.parent
        path = canonical(original)
        if not path.is_dir():
            raise ValueError(f"Escolha uma pasta: {path}")
        if any(within(path, other) for other in normalized):
            continue
        normalized = [other for other in normalized if not within(other, path)]
        normalized.append(path)
    return normalized


def scan(roots: list[Path | str], options: ScanOptions | None = None,
         cancel: threading.Event | None = None,
         progress: Callable[[ScanResult, Path], None] | None = None) -> ScanResult:
    options = options or ScanOptions()
    result = ScanResult([])
    protected = protected_paths()
    activity_cache: dict[Path, tuple[int, bool]] = {}
    enabled = {"Node.js": options.node, "Python venv": options.venv, "Cache Python": options.caches}
    last_update = 0.0
    try:
        for scope in normalize_roots(roots):
            stack = [scope]
            while stack:
                _cancelled(cancel)
                path = stack.pop()
                try:
                    if is_link(path) or path.name.lower() in SKIP_NAMES or any(within(path, p) for p in protected):
                        result.skipped += 1
                        continue
                    result.visited += 1
                    if progress and time.monotonic() - last_update > .2:
                        progress(result, path)
                        last_update = time.monotonic()
                    kind = kind_of(path)
                    if kind:
                        # Never descend into one dependency target to find nested duplicates.
                        if path == scope or not enabled[kind]:
                            result.skipped += 1
                            continue
                        info = path.stat()
                        snapshot = measure_tree(path, cancel)
                        project = find_project(path, scope)
                        if project not in activity_cache:
                            activity_cache[project] = project_activity(project, cancel)
                        newest, activity_complete = activity_cache[project]
                        blocked = ""
                        if not snapshot.complete or not activity_complete:
                            blocked = "Leitura incompleta; acesso ou limite de arquivos"
                        elif snapshot.has_links:
                            blocked = "Contém links/junções; somente inventário nesta versão"
                        result.candidates.append(Candidate(path, scope, project, kind, snapshot, newest,
                                                           (info.st_dev, info.st_ino), blocked))
                        continue
                    with os.scandir(path) as entries:
                        for entry in entries:
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(Path(entry.path))
                except OSError:
                    result.errors += 1
    except InterruptedError:
        result.cancelled = True
    result.candidates.sort(key=lambda item: item.snapshot.size, reverse=True)
    return result


def validate_candidate(candidate: Candidate, cancel: threading.Event | None = None) -> Path:
    """Fail closed if a recorded target, its scope or its contents have changed."""
    if candidate.blocked:
        raise ValueError(candidate.blocked)
    original = Path(os.path.abspath(candidate.path))
    path = canonical(original)
    scope = canonical(candidate.scope)
    if path != original or scope != candidate.scope or path == scope or not within(path, scope):
        raise ValueError("O caminho saiu da raiz escaneada ou foi redirecionado.")
    current = original
    while True:
        if is_link(current):
            raise ValueError("Há um link ou ponto de redirecionamento no caminho.")
        if current == scope:
            break
        current = current.parent
    if any(within(path, root) for root in protected_paths()):
        raise ValueError("A pasta pertence a uma instalação protegida.")
    info = path.stat()
    if (info.st_dev, info.st_ino) != candidate.identity or kind_of(path) != candidate.kind:
        raise ValueError("A pasta foi substituída. Faça uma nova busca.")
    updated = measure_tree(path, cancel)
    if updated != candidate.snapshot:
        raise ValueError("O conteúdo mudou desde a busca. Faça uma nova busca.")
    newest, complete = project_activity(candidate.project, cancel)
    if not complete or newest > candidate.project_newest_ns:
        raise ValueError("O projeto recebeu alterações desde a busca. Faça uma nova busca.")
    return path


def recycle_candidates(candidates: list[Candidate], recycle: Callable[[Path], None] | None = None,
                       cancel: threading.Event | None = None) -> list[tuple[Candidate, str]]:
    """Only accept scan records; JSON/CSV reports cannot authorize removal."""
    if recycle is None:
        from .windows import recycle_directory
        recycle = recycle_directory
    results = []
    processed: set[Path] = set()
    for candidate in candidates:
        _cancelled(cancel)
        if candidate.path in processed:
            continue
        processed.add(candidate.path)
        try:
            path = validate_candidate(candidate, cancel)
            recycle(path)
            if path.exists():
                raise OSError("O Windows não confirmou o envio à Lixeira.")
            results.append((candidate, "Enviado à Lixeira"))
        except (OSError, ValueError) as error:
            results.append((candidate, f"Não removido: {error}"))
    return results


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return str(value)


def inventory_report(candidates: list[Candidate], result: ScanResult | None = None) -> dict:
    """Build an informational report; never serialize cleanup authorization records."""
    return {
        "schema_version": 1,
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
        "scopes": sorted({str(item.scope) for item in candidates}),
        "visited": result.visited if result is not None else None,
        "errors": result.errors if result is not None else None,
        "skipped": result.skipped if result is not None else None,
        "cancelled": result.cancelled if result is not None else None,
        "logical_bytes": sum(item.snapshot.size for item in candidates),
        "candidates": [
            {"path": str(item.path), "project": str(item.project), "kind": item.kind,
             "logical_bytes": item.snapshot.size, "files": item.snapshot.files,
             "age_days": item.age_days(),
             "modified_at": datetime.fromtimestamp(item.newest_ns / 1e9, timezone.utc).isoformat(timespec="seconds"),
             "blocked": item.blocked}
            for item in candidates
        ],
    }


def export_json(candidates: list[Candidate], destination: Path, result: ScanResult | None = None) -> None:
    destination.write_text(json.dumps(inventory_report(candidates, result), ensure_ascii=True, indent=2) + "\n",
                           encoding="utf-8")


def export_csv(candidates: list[Candidate], destination: Path) -> None:
    def cell(value: object) -> str:
        text = str(value)
        return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Tipo", "Pasta", "Projeto", "Bytes lógicos", "Arquivos", "Dias sem alteração observada", "Última alteração observada", "Restrição"])
        for item in candidates:
            writer.writerow([cell(item.kind), cell(item.path), cell(item.project), item.snapshot.size,
                             item.snapshot.files, item.age_days(),
                             datetime.fromtimestamp(item.newest_ns / 1e9).isoformat(timespec="seconds"), cell(item.blocked)])
