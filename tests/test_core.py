import csv
import os
import subprocess
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from devsweep.core import (ScanOptions, export_csv, kind_of, measure_tree, normalize_roots,
                           recycle_candidates, scan, validate_candidate, within)


class ScannerTests(unittest.TestCase):
    def setUp(self):
        # All temporary trees, including their recursive cleanup, stay under this explicit root.
        self.sandbox = Path(os.environ.get("DEVSWEEP_TEST_ROOT", ".test-work")).absolute()
        self.sandbox.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="fixture-", dir=self.sandbox)
        self.root = Path(self.temp.name).resolve()
        assert within(self.root, self.sandbox.resolve())
        self.old = time.time() - 120 * 86400

    def tearDown(self):
        assert within(Path(self.temp.name).resolve(), self.sandbox.resolve())
        self.temp.cleanup()

    def file(self, path, data=b"test"):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def project(self, name="project", kind="node_modules"):
        self.file(f"{name}/package.json", b'{"name":"demo"}')
        path = self.file(f"{name}/{kind}/payload.bin", b"x" * 1024).parent
        if kind != "node_modules" and kind not in {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}:
            self.file(f"{name}/{kind}/pyvenv.cfg", b"home = C:\\Python\n")
        return path

    def age_all(self):
        paths = list(self.root.rglob("*"))
        for path in reversed(paths):
            if not path.is_symlink():
                os.utime(path, (self.old, self.old))
        os.utime(self.root, (self.old, self.old))

    def test_nodes_are_not_double_counted(self):
        target = self.project()
        self.file("project/node_modules/a/node_modules/b/index.js")
        result = scan([self.root])
        self.assertEqual([target], [item.path for item in result.candidates])
        self.assertEqual(1028, result.candidates[0].snapshot.size)

    def test_requires_venv_marker_not_folder_name(self):
        self.file("ordinary/venv/important.py")
        self.project("python", "custom-environment")
        result = scan([self.root])
        self.assertEqual(["Python venv"], [item.kind for item in result.candidates])

    def test_caches_and_environment_do_not_overlap(self):
        self.project("python", ".venv")
        self.file("python/.venv/lib/__pycache__/file.pyc")
        self.file("python/src/__pycache__/file.pyc")
        result = scan([self.root])
        self.assertEqual(2, len(result.candidates))

    def test_recent_source_prevents_old_age_classification(self):
        self.project()
        self.age_all()
        self.file("project/src/current.py")
        result = scan([self.root])
        self.assertEqual(0, result.candidates[0].age_days())

    def test_disabled_node_scan_does_not_descend_into_node_modules(self):
        self.project()
        self.file("project/node_modules/__pycache__/file.pyc")
        self.assertEqual([], scan([self.root], ScanOptions(node=False)).candidates)

    def test_overlapping_roots_are_deduplicated(self):
        self.project()
        roots = normalize_roots([self.root / "project", self.root, self.root])
        self.assertEqual([self.root], roots)
        self.assertEqual(1, len(scan([self.root, self.root / "project"]).candidates))

    def test_selected_scan_root_is_never_a_removal_candidate(self):
        target = self.project()
        self.assertEqual([], scan([target]).candidates)

    def test_protected_installation_is_skipped(self):
        self.project()
        with patch("devsweep.core.protected_paths", return_value=(self.root / "project",)):
            self.assertEqual([], scan([self.root]).candidates)

    def test_changed_dependencies_refuse_cleanup(self):
        target = self.project()
        candidate = scan([self.root]).candidates[0]
        (target / "new.txt").write_text("new")
        calls = []
        results = recycle_candidates([candidate], recycle=calls.append)
        self.assertEqual([], calls)
        self.assertTrue(target.exists())
        self.assertIn("Não removido", results[0][1])

    def test_changed_project_refuses_cleanup(self):
        self.project()
        self.age_all()
        candidate = scan([self.root]).candidates[0]
        self.file("project/new-source.py")
        with self.assertRaisesRegex(ValueError, "projeto recebeu"):
            validate_candidate(candidate)

    def test_outside_scope_refuses_cleanup(self):
        self.project()
        candidate = scan([self.root]).candidates[0]
        forged = replace(candidate, scope=candidate.path / "child")
        forged.scope.mkdir()
        with self.assertRaises(ValueError):
            validate_candidate(forged)

    def test_unmodified_target_passes_validation_without_deletion(self):
        target = self.project()
        candidate = scan([self.root]).candidates[0]
        self.assertEqual(target, validate_candidate(candidate))
        self.assertTrue(target.exists())

    def test_permission_failure_never_calls_recycler(self):
        self.project()
        candidate = scan([self.root]).candidates[0]
        calls = []
        with patch("devsweep.core.measure_tree", return_value=replace(candidate.snapshot, complete=False)):
            results = recycle_candidates([candidate], recycle=calls.append)
        self.assertFalse(calls)
        self.assertIn("Não removido", results[0][1])

    def test_cancelled_scan_returns_partial_state(self):
        self.project()
        event = threading.Event()
        event.set()
        self.assertTrue(scan([self.root], cancel=event).cancelled)

    def test_csv_is_report_only_and_contains_sizes(self):
        self.project()
        candidate = scan([self.root]).candidates[0]
        target = self.root / "report.csv"
        export_csv([candidate], target)
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(str(candidate.snapshot.size), rows[1][3])
        self.assertEqual(str(candidate.path), rows[1][1])

    def test_symlinks_are_not_followed_or_removed(self):
        target = self.project()
        try:
            (target / "linked").symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Criação de symlink não disponível nesta conta.")
        candidate = scan([self.root]).candidates[0]
        self.assertTrue(candidate.snapshot.has_links)
        self.assertTrue(candidate.blocked)
        with self.assertRaises(ValueError):
            validate_candidate(candidate)

    @unittest.skipUnless(os.name == "nt", "Junções são específicas do Windows.")
    def test_windows_junction_is_not_followed(self):
        target = self.project()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(target / "link"), str(outside)],
                                 capture_output=True, check=False)
        if created.returncode:
            self.skipTest("Criação de junção indisponível.")
        candidate = scan([self.root / "project"]).candidates[0]
        self.assertTrue(candidate.snapshot.has_links)
        self.assertEqual(1024, candidate.snapshot.size)
        with self.assertRaises(ValueError):
            validate_candidate(candidate)
        self.assertTrue((outside / "keep.txt").exists())

    @unittest.skipUnless(os.name == "nt", "Junções são específicas do Windows.")
    def test_scan_root_through_junction_is_rejected(self):
        target = self.project()
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.root / "alias"), str(target.parent)],
                                 capture_output=True, check=False)
        if created.returncode:
            self.skipTest("Criação de junção indisponível.")
        with self.assertRaisesRegex(ValueError, "redirecionamento"):
            normalize_roots([self.root / "alias" / "node_modules"])


if __name__ == "__main__":
    unittest.main()
