#!/usr/bin/env python3
"""
scaffolding-respa.py
=====================
Creates a new year's folder scaffolding for a respa/respa_junior
sub-competition: problem/solution/marking stub files for every
problem, plus ready-to-compile {theory,experiment}_{,sol,marking}.tex
root documents, for every grade x language the competition declares.
respa/final additionally gets an answer.tex stub per problem folder
and theory_answer.tex/experiment_answer.tex root documents -- see
HAS_ANSWER_SHEETS if another sub-competition adopts answer sheets later.

It does NOT touch manifest.yaml, strings-competition.tex, or
strings-manifest.tex -- manifest.yaml carries this year's real
dates/city and must be hand-written; the two strings-*.tex files are
created/completed from config.yaml/manifest.yaml by process-strings.py
(run it after this script, once manifest.yaml exists). The generated
root documents \\input all three, so compiling them for real still
needs them to exist. The script prints a reminder about this (and
about any missing competition-level files) when it's done.

Usage:
    python competitions/scaffolding-respa.py <base_dir> <name> [--force]

    base_dir   a sub-competition folder, e.g. competitions/respa/final
    name       the new folder to create under it, e.g. 2026-27

Examples:
    python competitions/scaffolding-respa.py competitions/respa/final 2026-27
    python competitions/scaffolding-respa.py competitions/respa/oblast 2026-27
    python competitions/scaffolding-respa.py competitions/respa/raion 2026-27
    python competitions/scaffolding-respa.py competitions/respa_junior/final 2026-27
    python competitions/scaffolding-respa.py competitions/respa_junior/oblast 2026-27

This file is specific to the respa family (respa/, respa_junior/).
A competition with a differently-shaped folder tree should get its
own scaffolding-<competition>.py rather than growing this one.
"""

from __future__ import annotations

import argparse
import re
import string
import sys
from pathlib import Path
from typing import NamedTuple

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


COMPETITIONS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = COMPETITIONS_ROOT.parent


# ============================================================
# EDIT HERE #1 — THE SHAPE OF EACH SUB-COMPETITION
# ============================================================
# This is the one place that answers "how many problems does this
# sub-competition have, and how are they named". Nothing here is
# read from any .yaml file -- the number/naming of problems is a
# structural fact about the competition format, not year-specific
# data, so it lives in code and gets edited by hand when the format
# itself changes (which should be rare).
#
# A Shape is:
#   theory      one entry per theory problem T1, T2, T3, ...
#                 0 (or 1)  -> a plain problem, folder "T<n>"
#                 k >= 2    -> a combined ("солянка") problem split
#                              into k lettered sub-parts, folders
#                              "T<n>A", "T<n>B", ... up to the k-th
#                              letter
#   experiment  how many experiment problems (E1, E2, ...) exist.
#                 0 means this sub-competition has no experiment tour
#                 at all -- no E folders and no experiment*.tex files
#                 are generated for it.
#
# To change an EXISTING sub-competition's problem count (e.g. if
# respa/oblast grows a 5th theory problem), edit its entry below.
class Shape(NamedTuple):
    theory: list[int]
    experiment: int


SHAPES: dict[str, Shape] = {
    # T1 is a солянка of 3 sub-parts (T1A/T1B/T1C), plus T2, T3, plus E1.
    "respa_final": Shape(theory=[3, 0, 0], experiment=1),
    # T1..T4, all plain, plus E1.
    "respa_oblast": Shape(theory=[0, 0, 0, 0], experiment=1),
    # T1..T4, all plain, no experiment tour at all.
    "four_theory_only": Shape(theory=[0, 0, 0, 0], experiment=0),
}

# ------------------------------------------------------------------
# Which sub-competition folder uses which shape. The key is the last
# two path components of the folder you pass on the command line
# (competition, sub-competition). Add a row here whenever a new
# sub-competition is introduced, or a new competition folder decides
# to reuse one of the shapes above (or add a new one in SHAPES).
SHAPE_BY_PATH: dict[tuple[str, str], str] = {
    ("respa", "final"): "respa_final",
    ("respa", "oblast"): "respa_oblast",
    ("respa", "raion"): "four_theory_only",
    ("respa_junior", "final"): "four_theory_only",
    ("respa_junior", "oblast"): "four_theory_only",
}

# ------------------------------------------------------------------
# Which sub-competitions also get an answer-sheet document, on top of
# the problem/solution/marking set every sub-competition gets: an
# answer.tex stub per problem folder, plus theory_answer.tex /
# experiment_answer.tex root documents. Only respa/final has answer
# sheets today; add a (competition, sub-competition) pair here if
# another stage adopts them later.
HAS_ANSWER_SHEETS: set[tuple[str, str]] = {
    ("respa", "final"),
}


# ============================================================
# EDIT HERE #2 — PLACEHOLDER TEXT AND DEFAULT POINT VALUES
# ============================================================
# Every generated stub starts out with this placeholder wording,
# always in Russian regardless of which language folder it lands in
# -- matching the existing hand-written stubs in respa/final/2025-26.
# Whoever authors the real problem overwrites both title and body
# (usually pasting in from an Overleaf submission), so the exact
# wording here never ships; it only needs to be unambiguous to the
# editor filling it in.
PLACEHOLDER_TITLE = "Название задачи"
PLACEHOLDER_PROBLEM_BODY = "Текст задачи"
PLACEHOLDER_SOLUTION_BODY = "Текст решения."
PLACEHOLDER_MARKING_COMMENT = (
    "% Здесь будет марк-схема; генерируется парсингом "
    "solution.tex скрипта extract-marking.py"
)
# answer.tex can't be meaningfully templated beyond the heading --
# how many blanks a problem needs, and their layout, depends entirely
# on the real problem text, which doesn't exist yet at scaffold time.
# Only respa/final uses this; see HAS_ANSWER_SHEETS above.
PLACEHOLDER_ANSWER_COMMENT = (
    "% Заполните бланк ответа с помощью \\begin{answerbox}{<высота>}...\\end{answerbox}\n"
    "% (или \\answerboxpart, если это часть солянки)."
)

# Default point values baked into the generated stubs. These are
# placeholders, not real point budgets for this specific year --
# the subproblem/problem point distribution is the one thing an
# editor is expected to hand-tune, and only until the author's real
# submission overwrites the whole file anyway.
POINTS_SUBPART = "3.0"  # each солянка sub-part (T1A, T1B, ...)
POINTS_COMBINED = "10.0"  # the combined солянка problem's own heading
POINTS_PROBLEM = "10.0"  # a plain, non-солянка theory problem
POINTS_EXPERIMENT = "15.0"  # an experiment problem

# The experiment's marking scheme uses the hand-authored `mse`
# environment (checklist-style criteria) rather than the
# \OlympMarkBeginTable pattern extract-marking.py generates for
# theory solutions -- experiments aren't step-by-step equation
# derivations, so there's nothing to extract from a solution.tex.
# This worked example is copied verbatim from the original
# respa/final/2025-26 scaffolding; its own first line tells the
# editor to delete it before filling in the real scheme.
PLACEHOLDER_EXPERIMENT_MARKING = r"""% Таблица ниже --- пример использования mse энвайронмента. Перед началом редактирования нужно удалить шаблон.

\begin{mse}
    \escheme{Проведено измерение ЭДС батареи}{0.5}

    \escheme{Найден ток при открытом диоде}{0.7}

    \escheme{Найдено сопротивление первого резистора}{0.5}

    % ...

    \blockbegin{Построена таблица зависимости $V(t)$. Баллы за измерения ставятся только если сами измерения и метод верные.}{1.8}{7}
        \bscheme{Измерено 15 и больше точек напряжения}{0.9}
        \bremark{Между 10 и 14 точками}{0.6/0.9}
        \bremark{Между 5 и 9}{0.3/0.9}
        \bscheme{Есть измерения при $t > \qty{20}{\s}$}{0.3}
        \bscheme{Есть измерения при $t < \qty{6}{\s}$}{0.3}
        \bscheme{Вычислены значения $\ln V$ для полученных точек}{0.3}
    \blockend

    % ...

    \etotal{15.0}
\end{mse}
"""


# ============================================================
# EDIT HERE #3 — YEAR-FOLDER-NAME -> CALENDAR-YEAR CONVENTION
# ============================================================
# Sub-competitions held in the FIRST half of the academic year --
# respa/raion runs in autumn, well before New Year -- instead of the
# second half. Everything else (oblast, final, and both junior
# stages) runs from mid-January onward, so the year folder's second
# half is the right calendar year for those, which is why this is an
# exception list rather than the default. Add a (competition,
# sub-competition) pair here if another early-in-the-year stage shows up.
FIRST_HALF_YEAR: set[tuple[str, str]] = {
    ("respa", "raion"),
}


def calendar_year_from_folder_name(name: str, comp: str, subcomp: str) -> str:
    """
    olympiad.cls's `year=` option wants a single 4-digit calendar
    year (the year the competition is actually held in), but folders
    are named after the academic year they belong to -- e.g.
    "2025-26" for the school year spanning 2025 into 2026.

    Most stages run from mid-January onward, i.e. in the SECOND
    calendar year of the academic year, so "2025-26" -> 2026 for
    those. Stages listed in FIRST_HALF_YEAR above (currently just
    respa/raion) run in autumn instead, in the FIRST calendar year,
    so "2025-26" -> 2025 for them.

    Also accepts a bare 4-digit year (e.g. "2027"), in case a
    sub-competition is ever folder-named directly by calendar year.
    Edit this function if a new naming convention shows up.
    """
    m = re.fullmatch(r"(\d{4})-(\d{2})", name)
    if m:
        first_half, second_half_suffix = m.group(1), m.group(2)
        if (comp, subcomp) in FIRST_HALF_YEAR:
            return first_half
        return first_half[:2] + second_half_suffix
    if re.fullmatch(r"\d{4}", name):
        return name
    raise SystemExit(
        f"Don't know how to turn folder name {name!r} into a calendar "
        f"year. Expected an academic-year 'YYYY-YY' (e.g. '2026-27') "
        f"or a bare 'YYYY'. Edit calendar_year_from_folder_name() if a "
        f"new naming convention is needed."
    )


# ============================================================
# config.yaml lookup — grades, languages, instructions only.
# Problem structure is NEVER read from yaml; see EDIT HERE #1.
# ============================================================
def load_competition_config(base_dir: Path) -> dict:
    rel_parts = base_dir.relative_to(COMPETITIONS_ROOT).parts
    for depth in range(len(rel_parts), 0, -1):
        comp_dir = COMPETITIONS_ROOT.joinpath(*rel_parts[:depth])
        candidate = comp_dir / "config.yaml"
        if candidate.is_file():
            raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            # config.yaml wraps everything in one top-level key named
            # after the competition (e.g. "respa:"); fall back to the
            # raw document if that key isn't there.
            data = raw.get(comp_dir.name, raw)
            grades = data.get("grades")
            languages = data.get("languages")
            if not grades or not languages:
                raise SystemExit(f"{candidate}: missing 'grades' or 'languages'.")
            return {
                "grades": list(grades),
                "languages": list(languages),
                "instructions": bool(data.get("instructions", True)),
            }
    raise SystemExit(
        f"No config.yaml found for competitions/{'/'.join(rel_parts)} "
        f"-- create competitions/{rel_parts[0]}/config.yaml first "
        f"(see competitions/respa/config.yaml as a template)."
    )


def validate_base_dir(base_dir: Path) -> tuple[str, str]:
    try:
        rel_parts = base_dir.relative_to(COMPETITIONS_ROOT).parts
    except ValueError:
        raise SystemExit(f"{base_dir} is not inside {COMPETITIONS_ROOT}")
    if len(rel_parts) != 2:
        raise SystemExit(
            f"Expected a sub-competition folder two levels under "
            f"competitions/ (e.g. competitions/respa/final), got "
            f"{base_dir} ({len(rel_parts)} level(s) under competitions/)."
        )
    return rel_parts[0], rel_parts[1]


# ============================================================
# Problem/solution/marking folder naming, derived from a Shape.
# ============================================================
def theory_problem_folders(shape: Shape) -> list[list[str]]:
    """
    One list of folder names per theory problem, e.g. for
    Shape(theory=[3, 0, 0], ...) -> [["T1A","T1B","T1C"], ["T2"], ["T3"]].
    A single-element inner list is a plain problem; more than one is
    a солянка split into that many lettered sub-parts.
    """
    groups = []
    for i, parts in enumerate(shape.theory, start=1):
        if parts and parts > 1:
            letters = string.ascii_uppercase[:parts]
            groups.append([f"T{i}{letter}" for letter in letters])
        else:
            groups.append([f"T{i}"])
    return groups


def experiment_problem_folders(shape: Shape) -> list[str]:
    return [f"E{i}" for i in range(1, shape.experiment + 1)]


# ============================================================
# Stub file contents (problem.tex / solution.tex / marking.tex)
# ============================================================
def problem_stub(is_subpart: bool, points: str) -> str:
    cmd = "subproblem" if is_subpart else "problem"
    return "\\" + cmd + "{" + PLACEHOLDER_TITLE + "}{" + points + "}\n\n" + PLACEHOLDER_PROBLEM_BODY + "\n"


def solution_stub(is_subpart: bool, points: str) -> str:
    cmd = "subsolution" if is_subpart else "solution"
    return "\\" + cmd + "{" + PLACEHOLDER_TITLE + "}{" + points + "}\n\n" + PLACEHOLDER_SOLUTION_BODY + "\n"


def answer_stub(is_subpart: bool, points: str) -> str:
    cmd = "subproblem" if is_subpart else "problem"
    return "\\" + cmd + "{" + PLACEHOLDER_TITLE + "}{" + points + "}\n\n" + PLACEHOLDER_ANSWER_COMMENT + "\n"


THEORY_MARKING_STUB = PLACEHOLDER_MARKING_COMMENT + "\n"


# ============================================================
# .latexmkrc rendering
# ============================================================
# latexmk only ever reads .latexmkrc from three fixed places -- system,
# $HOME, and the literal current directory -- it never walks up parent
# directories looking for one (this is a property of latexmk.pl's own
# rc-search code, not a guess). So every directory a document gets
# compiled from still needs a file with this exact name, but it doesn't
# need to duplicate the real config: it just loads qazpho-latex/.latexmkrc
# (found via `git rev-parse --show-toplevel`, so it works at any nesting
# depth without adjustment). Edit the root .latexmkrc, not this stub,
# when the shared TEXINPUTS/pdf_mode config needs to change.
def render_latexmkrc() -> str:
    lines = [
        "# Stub only -- see qazpho-latex/.latexmkrc for the real config and",
        "# competitions/scaffolding-respa.py's render_latexmkrc() for why this",
        "# file has to exist here at all.",
        "my $root = `git rev-parse --show-toplevel`;",
        "chomp($root);",
        'do "$root/.latexmkrc";',
        "",
    ]
    return "\n".join(lines)


# ============================================================
# Root document rendering: theory/experiment x problems/solutions/marking
# ============================================================
def _preamble(*, lang: str, calendar_year: str, grade: str, tour: str, doc_type: str, comp: str, subcomp: str, year_name: str) -> list[str]:
    lines = [
        r"\documentclass[",
        f"  language={lang},",
        f"  year={calendar_year},",
        f"  grade={grade},",
        f"  tour={tour},",
        f"  type={doc_type},",
        r"  style=respa",  # this script is respa-family-only; see module docstring
        r"]{olympiad}",
        "",
        r"\usepackage{olympiad-layout}",
        r"\usepackage{olympiad-units-" + lang + "}",
    ]
    if doc_type in ("solutions", "marking"):
        lines.append(r"\usepackage{olympiad-marking}")
    lines += [
        "",
        r"\input{competitions/" + comp + "/strings-config.tex}",
        r"\input{competitions/" + comp + "/" + subcomp + "/strings-competition.tex}",
        r"\input{competitions/" + comp + "/" + subcomp + "/" + year_name + "/strings-manifest.tex}",
        "",
        r"\begin{document}",
    ]
    return lines


def render_problems_doc(
    *, groups: list[list[str]], soljanka_indices: set[int], instructions: bool,
    lang: str, calendar_year: str, grade: str, tour: str, comp: str, subcomp: str, year_name: str,
) -> str:
    lines = _preamble(lang=lang, calendar_year=calendar_year, grade=grade, tour=tour,
                       doc_type="problems", comp=comp, subcomp=subcomp, year_name=year_name)
    lines += [
        "",
        r"\input{competitions/" + comp + "/title_" + lang + ".tex}",
        "",
        r"\newpage",
        "",
    ]
    if instructions:
        lines += [
            r"\input{competitions/" + comp + "/instructions/" + tour + "_" + lang + ".tex}",
            "",
            r"\newpage",
            "",
        ]
    lines.append(r"\problemsheader")
    for i, folders in enumerate(groups):
        if i in soljanka_indices:
            lines += [
                r"\problem{\OlympString{soljanka}}{" + POINTS_COMBINED + "}",
                r"\centerline{\OlympString{soljanka_header}}",
                "",
            ]
        for folder in folders:
            lines.append(r"\input{" + folder + "/problem.tex}")
        if i != len(groups) - 1:
            lines += ["", r"\newpage", ""]
    lines += ["", r"\end{document}", ""]
    return "\n".join(lines)


def render_answer_doc(
    *, groups: list[list[str]], soljanka_indices: set[int],
    lang: str, calendar_year: str, grade: str, tour: str, comp: str, subcomp: str, year_name: str,
) -> str:
    # Answer sheets reuse type=problems (there's no dedicated type in
    # olympiad.cls for them) and skip the title page/instructions that
    # render_problems_doc adds -- \answersheetsheader is the only
    # heading, matching \solutionsheader/\markingheader's pattern of
    # never showing the cover page to graders/answer-checkers either.
    lines = _preamble(lang=lang, calendar_year=calendar_year, grade=grade, tour=tour,
                       doc_type="problems", comp=comp, subcomp=subcomp, year_name=year_name)
    lines += [r"\answersheetsheader", ""]
    for i, folders in enumerate(groups):
        if i in soljanka_indices:
            lines.append(r"\problem{\OlympString{soljanka}}{" + POINTS_COMBINED + "}")
        for folder in folders:
            lines.append(r"\input{" + folder + "/answer.tex}")
        if i != len(groups) - 1:
            lines += ["", r"\newpage", ""]
    lines += ["", r"\end{document}", ""]
    return "\n".join(lines)


def render_solutions_doc(
    *, groups: list[list[str]], soljanka_indices: set[int],
    lang: str, calendar_year: str, grade: str, tour: str, comp: str, subcomp: str, year_name: str,
) -> str:
    lines = _preamble(lang=lang, calendar_year=calendar_year, grade=grade, tour=tour,
                       doc_type="solutions", comp=comp, subcomp=subcomp, year_name=year_name)
    lines.append(r"\solutionsheader")
    for i, folders in enumerate(groups):
        if i in soljanka_indices:
            lines += [
                "",
                r"\solution{\OlympString{soljanka}}{" + POINTS_COMBINED + "}",
            ]
        lines.append("")
        for folder in folders:
            lines.append(r"\input{" + folder + "/solution.tex}")
            lines.append("")
            lines.append(r"\input{" + folder + "/marking.tex}")
            lines.append("")
    lines += [r"\end{document}", ""]
    return "\n".join(lines)


def render_marking_doc(
    *, groups: list[list[str]],
    lang: str, calendar_year: str, grade: str, tour: str, comp: str, subcomp: str, year_name: str,
) -> str:
    lines = _preamble(lang=lang, calendar_year=calendar_year, grade=grade, tour=tour,
                       doc_type="marking", comp=comp, subcomp=subcomp, year_name=year_name)
    lines.append("")
    for i, folders in enumerate(groups):
        lines.append(r"\markingheader")
        for folder in folders:
            lines.append(r"\input{" + folder + "/marking.tex}")
        if i != len(groups) - 1:
            lines += ["", r"\newpage", ""]
    lines += ["", r"\end{document}", ""]
    return "\n".join(lines)


# ============================================================
# Misc helpers
# ============================================================
def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def check_competition_level_files(comp: str, subcomp: str, lang: str, instructions: bool, tours: list[str]) -> set[str]:
    """
    These live above the year folder and are set up once per
    competition/sub-competition (not generated by this script) --
    title_<lang>.tex, strings-config.tex, strings-competition.tex, and
    (if instructions=true) the per-tour instructions page. Just warn if
    they're not there yet -- process-strings.py creates/completes the
    two strings-*.tex files from config.yaml/manifest.yaml.
    """
    missing = set()
    comp_dir = COMPETITIONS_ROOT / comp
    checks = [f"strings-config.tex", f"title_{lang}.tex"]
    if instructions:
        checks += [f"instructions/{tour}_{lang}.tex" for tour in tours]
    for rel in checks:
        if not (comp_dir / rel).is_file():
            missing.add(f"competitions/{comp}/{rel}")
    if not (comp_dir / subcomp / "strings-competition.tex").is_file():
        missing.add(f"competitions/{comp}/{subcomp}/strings-competition.tex")
    return missing


# ============================================================
# Orchestration
# ============================================================
def scaffold_year(base_dir: Path, year_name: str, force: bool) -> None:
    if "/" in year_name or "\\" in year_name:
        raise SystemExit(f"name must be a single folder name, not a path: {year_name!r}")

    base_dir = base_dir.resolve()
    comp, subcomp = validate_base_dir(base_dir)

    shape_key = SHAPE_BY_PATH.get((comp, subcomp))
    if shape_key is None:
        known = ", ".join(f"{c}/{s}" for c, s in SHAPE_BY_PATH)
        raise SystemExit(
            f"Don't know the problem-structure 'shape' for "
            f"competitions/{comp}/{subcomp}/. Known sub-competitions: "
            f"{known}. Add an entry to SHAPE_BY_PATH (and SHAPES if "
            f"it's a genuinely new shape) near the top of this file."
        )
    shape = SHAPES[shape_key]

    cfg = load_competition_config(base_dir)

    year_dir = base_dir / year_name
    if year_dir.exists() and not force:
        raise SystemExit(
            f"{year_dir} already exists. Pass --force to regenerate "
            f"scaffolding files inside it (this only overwrites the "
            f"files this script itself writes -- problem.tex/solution.tex/"
            f"marking.tex and the root documents -- never manifest.yaml, "
            f"strings-manifest.tex, or figures/)."
        )

    calendar_year = calendar_year_from_folder_name(year_name, comp, subcomp)
    theory_groups = theory_problem_folders(shape)
    soljanka_indices = {i for i, g in enumerate(theory_groups) if len(g) > 1}
    experiment_folders = experiment_problem_folders(shape)
    experiment_groups = [[f] for f in experiment_folders]

    print(f"Scaffolding {year_dir}")
    print(f"  shape: {shape_key}  (theory={shape.theory}, experiment={shape.experiment})")
    print(f"  grades: {cfg['grades']}   languages: {cfg['languages']}   instructions: {cfg['instructions']}")

    missing_competition_files: set[str] = set()
    tours = ["theory"] + (["experiment"] if shape.experiment else [])
    wants_answers = (comp, subcomp) in HAS_ANSWER_SHEETS

    for grade in cfg["grades"]:
        grade_dir = year_dir / str(grade)
        (grade_dir / "figures").mkdir(parents=True, exist_ok=True)

        for lang in cfg["languages"]:
            lang_dir = grade_dir / str(lang)

            write_file(lang_dir / ".latexmkrc", render_latexmkrc())

            for group in theory_groups:
                is_split = len(group) > 1
                points = POINTS_SUBPART if is_split else POINTS_PROBLEM
                for folder in group:
                    folder_dir = lang_dir / folder
                    write_file(folder_dir / "problem.tex", problem_stub(is_split, points))
                    write_file(folder_dir / "solution.tex", solution_stub(is_split, points))
                    write_file(folder_dir / "marking.tex", THEORY_MARKING_STUB)
                    if wants_answers:
                        write_file(folder_dir / "answer.tex", answer_stub(is_split, points))

            for folder in experiment_folders:
                folder_dir = lang_dir / folder
                write_file(folder_dir / "problem.tex", problem_stub(False, POINTS_EXPERIMENT))
                write_file(folder_dir / "solution.tex", solution_stub(False, POINTS_EXPERIMENT))
                write_file(folder_dir / "marking.tex", PLACEHOLDER_EXPERIMENT_MARKING)
                if wants_answers:
                    write_file(folder_dir / "answer.tex", answer_stub(False, POINTS_EXPERIMENT))

            common = dict(lang=lang, calendar_year=calendar_year, grade=str(grade),
                          comp=comp, subcomp=subcomp, year_name=year_name)

            write_file(lang_dir / "theory.tex", render_problems_doc(
                groups=theory_groups, soljanka_indices=soljanka_indices,
                instructions=cfg["instructions"], tour="theory", **common))
            write_file(lang_dir / "theory_sol.tex", render_solutions_doc(
                groups=theory_groups, soljanka_indices=soljanka_indices, tour="theory", **common))
            write_file(lang_dir / "theory_marking.tex", render_marking_doc(
                groups=theory_groups, tour="theory", **common))
            if wants_answers:
                write_file(lang_dir / "theory_answer.tex", render_answer_doc(
                    groups=theory_groups, soljanka_indices=soljanka_indices, tour="theory", **common))

            if shape.experiment > 0:
                write_file(lang_dir / "experiment.tex", render_problems_doc(
                    groups=experiment_groups, soljanka_indices=set(),
                    instructions=cfg["instructions"], tour="experiment", **common))
                write_file(lang_dir / "experiment_sol.tex", render_solutions_doc(
                    groups=experiment_groups, soljanka_indices=set(), tour="experiment", **common))
                write_file(lang_dir / "experiment_marking.tex", render_marking_doc(
                    groups=experiment_groups, tour="experiment", **common))
                if wants_answers:
                    write_file(lang_dir / "experiment_answer.tex", render_answer_doc(
                        groups=experiment_groups, soljanka_indices=set(), tour="experiment", **common))

            missing_competition_files |= check_competition_level_files(
                comp, subcomp, lang, cfg["instructions"], tours)

    print()
    print("Done. Still needed before this actually compiles:")
    print(f"  - {year_dir / 'manifest.yaml'} (this year's real dates/city)")
    print(f"  - then run: python process-strings.py {year_dir}")
    print(f"    (creates/completes strings-competition.tex and strings-manifest.tex")
    print(f"    from config.yaml/manifest.yaml, and reports anything it can't derive)")
    if missing_competition_files:
        print()
        print("  These competition-level files (shared by every year) don't exist yet:")
        for f in sorted(missing_competition_files):
            print(f"    - {f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a new year for a respa/respa_junior sub-competition.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("base_dir", type=Path, help="e.g. competitions/respa/final")
    parser.add_argument("name", help="new folder name to create, e.g. 2026-27")
    parser.add_argument("--force", action="store_true",
                         help="overwrite scaffolding files if the year folder already exists")
    args = parser.parse_args()
    scaffold_year(args.base_dir, args.name, args.force)


if __name__ == "__main__":
    main()
