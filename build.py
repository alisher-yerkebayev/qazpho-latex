#!/usr/bin/env python3
"""
build.py
========
Compiles competition documents to PDF, and collects finished PDFs for
one competition-year into a flat dist/ folder.

Usage:
    python build.py compile <target>
    python build.py dist <year_dir>

    target     a single .tex file, or a directory (year/grade/language
               folder, or anything in between) -- every root document
               found under it gets (re)compiled
    year_dir   e.g. competitions/respa/final/2025-26

Examples:
    python build.py compile competitions/respa/final/2025-26
    python build.py compile competitions/respa/final/2025-26/11/ru/theory.tex
    python build.py dist competitions/respa/final/2025-26

"compile" always reruns latexmk and overwrites whatever PDF is already
in that document's build/ folder -- there's no staleness/mtime check.
It relies entirely on the .latexmkrc stub -> root .latexmkrc chain for
TEXINPUTS and font search paths (see qazpho-latex/.latexmkrc); it does
not set any LaTeX environment variables itself. This means latexmk
must be on PATH and the current checkout must have `git` available,
same requirement the .latexmkrc stubs already impose. Compiles run
under XeLaTeX (`-pdfxe`) -- olympiad.cls requires it (fontspec-based
per-style fonts; see olympiad.cls's v1.5 changelog).

"dist" names each copied PDF {family}_{stage}{year}_{grade}_{stem}_{lang}.pdf,
e.g. respa_final2026_11_theory_answer_ru.pdf -- family/stage come from
year_dir's own path, year comes from manifest.yaml's dates.year (the
calendar year actually being built for, not the "2025-26"-style academic
year folder name), grade/lang come from the two path components directly
above each build/ folder, and stem is the PDF's own filename stem.

"dist" skips any *_jury.pdf (theory_jury.pdf/experiment_jury.pdf,
type=jury -- the internal, jury-only dense scheme table with fields
for the grader's name/cipher, see olympiad-marking.sty's \\juryheader):
those aren't meant to leave the grading room, unlike the optional,
student-facing *_marking.pdf (type=marking) built from the same
marking.tex fragments, which IS meant for dist.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


REPO_ROOT = Path(__file__).resolve().parent

_PRUNED_DIR_NAMES = {"build", "figures"}


def _strip_comment(line: str) -> str:
    """Truncate a line at its first unescaped '%' (LaTeX comment start),
    so a doc comment that merely mentions "\\documentclass" as example
    text doesn't get mistaken for a real declaration."""
    out = []
    i = 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2])
            i += 2
            continue
        if line[i] == "%":
            break
        out.append(line[i])
        i += 1
    return "".join(out)


def _is_root_document(tex_file: Path) -> bool:
    """A root document has its own \\documentclass -- unlike per-problem
    fragments (T1A/problem.tex etc.), which get \\input by one."""
    try:
        lines = tex_file.read_text(encoding="utf-8", errors="ignore").splitlines()[:30]
    except OSError:
        return False
    return any("\\documentclass" in _strip_comment(line) for line in lines)


def find_root_documents(target: Path) -> list[Path]:
    if target.is_file():
        if target.suffix != ".tex":
            raise SystemExit(f"{target} is not a .tex file.")
        return [target]
    if not target.is_dir():
        raise SystemExit(f"{target} does not exist.")

    found = []
    stack = [target]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if entry.is_dir():
                if entry.name not in _PRUNED_DIR_NAMES and not entry.name.startswith("."):
                    stack.append(entry)
            elif entry.suffix == ".tex" and _is_root_document(entry):
                found.append(entry)
    return sorted(found)


def compile_one(tex_file: Path) -> bool:
    """Returns True on success."""
    result = subprocess.run(
        ["latexmk", "-pdfxe", "-interaction=nonstopmode", "-halt-on-error", "-outdir=build", tex_file.name],
        cwd=tex_file.parent,
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    rel = tex_file.relative_to(REPO_ROOT) if REPO_ROOT in tex_file.parents else tex_file
    if ok:
        print(f"OK: {rel}")
    else:
        log = tex_file.parent / "build" / f"{tex_file.stem}.log"
        print(f"FAILED: {rel} (see {log.relative_to(REPO_ROOT) if REPO_ROOT in log.parents else log})")
    return ok


def cmd_compile(target: Path) -> None:
    docs = find_root_documents(target.resolve())
    if not docs:
        raise SystemExit(f"No root documents (files containing \\documentclass) found under {target}.")
    print(f"Found {len(docs)} document(s) to compile.")
    results = [compile_one(doc) for doc in docs]
    succeeded = sum(results)
    failed = len(results) - succeeded
    print()
    print(f"{succeeded} succeeded, {failed} failed.")
    if failed:
        sys.exit(1)


# ============================================================
# dist
# ============================================================
def parse_year_dir(year_dir: Path) -> tuple[str, str, str]:
    year_dir = year_dir.resolve()
    try:
        rel_parts = year_dir.relative_to(REPO_ROOT / "competitions").parts
    except ValueError:
        raise SystemExit(f"{year_dir} is not inside {REPO_ROOT / 'competitions'}")
    if len(rel_parts) != 3:
        raise SystemExit(
            f"Expected competitions/<family>/<stage>/<year> (3 levels under "
            f"competitions/), got {year_dir} ({len(rel_parts)} level(s))."
        )
    family, stage, year_name = rel_parts
    return family, stage, year_name


def cmd_dist(year_dir: Path) -> None:
    family, stage, _year_name = parse_year_dir(year_dir)
    year_dir = year_dir.resolve()

    manifest_path = year_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise SystemExit(f"{manifest_path} does not exist -- dist needs it for the calendar year.")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    try:
        year = manifest["dates"]["year"]
    except KeyError:
        raise SystemExit(f"{manifest_path}: missing dates.year.")

    all_pdfs = sorted(year_dir.glob("*/*/build/*.pdf"))
    if not all_pdfs:
        raise SystemExit(f"No PDFs found under {year_dir}/*/*/build/ -- run `build.py compile` first.")

    pdfs = [pdf for pdf in all_pdfs if not pdf.stem.endswith("_jury")]
    skipped_jury = [pdf for pdf in all_pdfs if pdf.stem.endswith("_jury")]

    dist_dir = year_dir / "dist"
    dist_dir.mkdir(exist_ok=True)

    copied = []
    for pdf in pdfs:
        grade = pdf.parent.parent.parent.name
        lang = pdf.parent.parent.name
        dest_name = f"{family}_{stage}{year}_{grade}_{pdf.stem}_{lang}.pdf"
        shutil.copy2(pdf, dist_dir / dest_name)
        copied.append(dest_name)

    print(f"Copied {len(copied)} file(s) into {dist_dir.relative_to(REPO_ROOT)}:")
    for name in copied:
        print(f"  {name}")
    if skipped_jury:
        print(f"Skipped {len(skipped_jury)} internal-only jury PDF(s) (not meant for dist):")
        for pdf in skipped_jury:
            print(f"  {pdf.relative_to(year_dir)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile competition documents and collect PDFs for a competition-year.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_compile = subparsers.add_parser("compile", help="compile all root documents under target (or a single file)")
    p_compile.add_argument("target", type=Path)

    p_dist = subparsers.add_parser("dist", help="collect build/*.pdf files into <year_dir>/dist/")
    p_dist.add_argument("year_dir", type=Path)

    args = parser.parse_args()
    if args.command == "compile":
        cmd_compile(args.target)
    elif args.command == "dist":
        cmd_dist(args.year_dir)


if __name__ == "__main__":
    main()
