"""Default: GUI. Command-line scanning is read-only."""
import argparse
import json
from pathlib import Path

from . import __version__
from .core import ScanOptions, export_csv, format_size, inventory_report, scan


def main():
    parser = argparse.ArgumentParser(description="DevSweep: inventário de dependências Node.js e Python.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--scan", nargs="+", metavar="PASTA", help="Busca somente leitura; sem este argumento abre a interface.")
    parser.add_argument("--days", type=int, default=60, help="Mínimo de dias sem alteração observada (padrão: 60).")
    parser.add_argument("--min-mb", type=float, default=10, help="Tamanho lógico mínimo em MiB (padrão: 10).")
    parser.add_argument("--csv", type=Path, help="Salvar inventário CSV neste arquivo.")
    parser.add_argument("--json", action="store_true", help="Exibir JSON na saída padrão.")
    parser.add_argument("--no-caches", action="store_true", help="Não inventariar caches Python.")
    args = parser.parse_args()
    if args.scan is None:
        from .app import main as gui_main
        gui_main()
        return 0
    if args.days < 0 or args.min_mb < 0 or not __import__("math").isfinite(args.min_mb):
        parser.error("Filtros precisam ser números finitos a partir de zero.")
    try:
        result = scan(args.scan, ScanOptions(caches=not args.no_caches))
        candidates = [item for item in result.candidates if item.age_days() >= args.days and item.snapshot.size >= args.min_mb * 1024**2]
        if args.csv:
            export_csv(candidates, args.csv)
        if args.json:
            print(json.dumps(inventory_report(candidates, result), ensure_ascii=True, indent=2))
        else:
            for item in candidates:
                print(f"{item.kind:12} {format_size(item.snapshot.size):>11} {item.age_days():>5} dias  {item.path}")
                if item.blocked:
                    print(f"  Somente inventário: {item.blocked}")
            print(f"\n{len(candidates)} pastas | {format_size(sum(item.snapshot.size for item in candidates))} lógicos | somente leitura")
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, f"DevSweep: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
