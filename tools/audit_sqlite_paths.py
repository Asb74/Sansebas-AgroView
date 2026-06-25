from __future__ import annotations

import argparse
from pathlib import Path

IGNORED_DIRS = {"reports", "tools", "tests", "__pycache__", ".git"}
SQLITE_PATTERNS = ("sqlite", ".db", "DBPedidos", "DBfruta", "bdloteado", "BdCalidad")
PYTHON_SUFFIXES = {".py"}


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        yield path


def audit_sqlite_paths(root: Path) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for path in iter_python_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(encoding="latin-1").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if any(pattern in line for pattern in SQLITE_PATTERNS):
                findings.append((path, line_number, line.strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita referencias a rutas/archivos SQLite en el código de la app.")
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    for path, line_number, line in audit_sqlite_paths(root):
        print(f"{path.relative_to(root)}:{line_number}: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
