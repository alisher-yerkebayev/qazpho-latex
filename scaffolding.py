#!/usr/bin/env python3
"""
scaffolding.py
==============
Interactive scaffolder for a new year (or first year) of a competition
stage: problem/solution/marking stub files for every problem, plus
ready-to-compile root documents, for every grade x language the stage
declares.

Unlike its predecessor (competitions/scaffolding-respa.py, now
deleted), this script does not hard-code which competition families
exist or read a config.yaml for grades/languages/instructions -- it
asks you, interactively, every time it runs:

  - which academic year this is for (it derives the "yyyy-yy" folder
    name from the calendar year the academic year starts in)
  - respa / respa_junior / a custom family, and which stage
  - (custom only) grades, languages, and the tour layout: either the
    standard theory/experiment split (with however many problems, and
    however many сombined "солянка" sub-parts each has), or a bare
    tour1/tour2/.../tourN split for a format that doesn't fit that mold

respa and respa_junior keep their known shape (problem counts,
солянка splits, which stages get answer sheets) exactly as
scaffolding-respa.py had them hard-coded -- see FAMILY SHAPES below --
because that structural data doesn't change from run to run and isn't
config.yaml's job to carry. What config.yaml *did* carry for those two
families (grades, languages, whether there's an instructions page) is
now hard-coded alongside the shapes in FAMILY_DEFAULTS, for the same
reason: it's a structural fact about the family, and it was the only
thing in this script that still touched a YAML file.

It does NOT touch manifest.yaml, strings-config.tex,
strings-competition.tex, or strings-manifest.tex -- manifest.yaml
carries this year's real dates/city and must be hand-written; the
three strings-*.tex files are created/completed from
config.yaml/manifest.yaml by process-strings.py (run it after this
script, once manifest.yaml exists -- that script's own config.yaml
usage is unrelated to this one and out of this script's scope). The
generated root documents \\input all three, so compiling them for real
still needs them to exist. This script prints a reminder about that
(and about any missing family-level files) when it's done.

Usage:
    python scaffolding.py

Run it from anywhere inside the repo; every question has a prompt
explaining what's expected, and folder names/paths are shown as the
script builds them up.
"""

from __future__ import annotations

import re
import string
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent
COMPETITIONS_ROOT = REPO_ROOT / "competitions"


# ============================================================
# FAMILY SHAPES -- respa / respa_junior structural data
# ============================================================
# This is the one place that answers "how many problems does this
# stage have, and how are they named" for the two known families.
# Nothing here is read from any .yaml file -- the number/naming of
# problems is a structural fact about the competition format, not
# year-specific data, so it lives in code and gets edited by hand when
# the format itself changes (which should be rare). A custom family
# never touches this table -- its shape is asked for interactively
# instead, once per run (see ask_custom_shape()).
#
# A Shape is:
#   theory      one entry per theory problem T1, T2, T3, ...
#                 0 (or 1)  -> a plain problem, folder "T<n>"
#                 k >= 2    -> a combined ("солянка") problem split
#                              into k lettered sub-parts, folders
#                              "T<n>A", "T<n>B", ... up to the k-th
#                              letter
#   experiment  how many experiment problems (E1, E2, ...) exist.
#                 0 means this stage has no experiment tour at all --
#                 no E folders and no experiment*.tex files are
#                 generated for it.
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
# Which stage uses which shape. Add a row here whenever a new respa/
# respa_junior stage is introduced, or decides to reuse one of the
# shapes above (or add a new one in SHAPES). This is also the source
# of truth for which stages exist under each family -- the "which
# stage?" prompt below only offers stages listed here.
SHAPE_BY_PATH: dict[tuple[str, str], str] = {
    ("respa", "final"): "respa_final",
    ("respa", "oblast"): "respa_oblast",
    ("respa", "raion"): "four_theory_only",
    ("respa_junior", "final"): "four_theory_only",
    ("respa_junior", "oblast"): "four_theory_only",
}

# ------------------------------------------------------------------
# Which stages also get an answer-sheet document, on top of the
# problem/solution/marking set every stage gets: an answer.tex stub
# per problem folder, plus theory_answer.tex/experiment_answer.tex
# root documents. Only respa/final has answer sheets today; add a
# (family, stage) pair here if another stage adopts them later. A
# custom family is asked about this directly instead.
HAS_ANSWER_SHEETS: set[tuple[str, str]] = {
    ("respa", "final"),
}

# ------------------------------------------------------------------
# Stages held in the FIRST half of the academic year -- respa/raion
# runs in autumn, well before New Year -- instead of the second half.
# Everything else (oblast, final, and both junior stages) runs from
# mid-January onward, so the year folder's second half is the right
# calendar year for those, which is why this is an exception list
# rather than the default. A custom family is asked directly instead
# of consulting this table.
FIRST_HALF_YEAR: set[tuple[str, str]] = {
    ("respa", "raion"),
}

# ------------------------------------------------------------------
# Grades/languages/instructions per family -- this used to live in
# competitions/<family>/config.yaml; it's hard-coded here instead for
# the same reason SHAPES is: it's a structural fact about the family
# (which grades and languages it's offered in), not year-specific
# data, so editing it by hand when a family's grades/languages
# actually change is the right amount of ceremony. A custom family is
# asked for its grades/languages/instructions directly instead.
FAMILY_DEFAULTS: dict[str, dict] = {
    "respa": {"grades": [9, 10, 11], "languages": ["ru", "kz"], "instructions": True},
    "respa_junior": {"grades": [7, 8], "languages": ["ru", "kz"], "instructions": True},
}


# ============================================================
# Placeholder text and default point values
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
# answer.tex can't be meaningfully templated beyond the heading -- how
# many blanks a problem needs, and their layout, depends entirely on
# the real problem text, which doesn't exist yet at scaffold time.
PLACEHOLDER_ANSWER_COMMENT = (
    "% Заполните бланк ответа с помощью \\begin{answerbox}{<высота>}...\\end{answerbox}\n"
    "% (или \\answerboxpart, если это часть солянки)."
)

# Default point values baked into the generated stubs. These are
# placeholders, not real point budgets for this specific year -- the
# subproblem/problem point distribution is the one thing an editor is
# expected to hand-tune, and only until the author's real submission
# overwrites the whole file anyway.
POINTS_SUBPART = "3.0"  # each солянка sub-part (T1A, T1B, ...)
POINTS_COMBINED = "10.0"  # the combined солянка problem's own heading
POINTS_PROBLEM = "10.0"  # a plain, non-солянка theory problem
POINTS_EXPERIMENT = "15.0"  # an experiment problem

# The experiment's marking scheme uses the hand-authored `mse`
# environment (checklist-style criteria) rather than the
# \OlympMarkBeginTable pattern extract-marking.py generates for theory
# solutions -- experiments aren't step-by-step equation derivations,
# so there's nothing to extract from a solution.tex. This worked
# example is copied verbatim from the original respa/final/2025-26
# scaffolding; its own first line tells the editor to delete it before
# filling in the real scheme.
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
# Interactive prompt helpers
# ============================================================
def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise SystemExit("\nAborted -- nothing written.")


def choose(prompt: str, choices: list[tuple[str, str]]) -> str:
    """choices is a list of (key, label); returns the chosen key."""
    print(prompt)
    for i, (_key, label) in enumerate(choices, start=1):
        print(f"  {i}) {label}")
    while True:
        raw = ask("> ")
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][0]
        print(f"Enter a number from 1 to {len(choices)}.")


def ask_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        raw = ask(prompt)
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"Enter a whole number from {lo} to {hi}.")


def ask_yes_no(prompt: str, default: bool) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        raw = ask(prompt + suffix).lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Enter y or n.")


def ask_list(prompt: str) -> list[str]:
    while True:
        raw = ask(prompt)
        items = [item.strip() for item in raw.split(",") if item.strip()]
        if items:
            return items
        print("Enter at least one value, comma-separated.")


def ask_foldername(prompt: str) -> str:
    while True:
        raw = ask(prompt)
        if not raw:
            print("This can't be empty.")
        elif "/" in raw or "\\" in raw:
            print("Enter a single folder name, not a path.")
        else:
            return raw


def ask_start_year() -> int:
    while True:
        raw = ask(
            "What calendar year does this Olympiad's academic year start in "
            "(will it be 2025 or 2026, or another year)? "
        )
        if re.fullmatch(r"\d{4}", raw):
            return int(raw)
        print("Enter a 4-digit year, e.g. 2025.")


# ============================================================
# Folder naming, derived from a Shape (unchanged from scaffolding-respa.py)
# ============================================================
def theory_problem_folders(shape: Shape) -> list[list[str]]:
    """
    One list of folder names per theory problem, e.g. for
    Shape(theory=[3, 0, 0], ...) -> [["T1A","T1B","T1C"], ["T2"], ["T3"]].
    A single-element inner list is a plain problem; more than one is a
    солянка split into that many lettered sub-parts.
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
        "# scaffolding.py's render_latexmkrc() for why this file has to",
        "# exist here at all.",
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
        r"  style=respa",  # the only layout style olympiad.cls supports today
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


def validate_base_dir(base_dir: Path) -> tuple[str, str]:
    try:
        rel_parts = base_dir.relative_to(COMPETITIONS_ROOT).parts
    except ValueError:
        raise SystemExit(f"{base_dir} is not inside {COMPETITIONS_ROOT}")
    if len(rel_parts) != 2:
        raise SystemExit(
            f"Expected a stage folder two levels under competitions/ "
            f"(e.g. competitions/respa/final), got {base_dir} "
            f"({len(rel_parts)} level(s) under competitions/)."
        )
    return rel_parts[0], rel_parts[1]


def check_competition_level_files(comp: str, subcomp: str, lang: str, instructions: bool, tours: list[str]) -> set[str]:
    """
    These live above the year folder and are set up once per
    family/stage (not generated by this script) -- title_<lang>.tex,
    strings-config.tex, strings-competition.tex, and (if
    instructions=true) the per-tour instructions page. Just warn if
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


def confirm_year_dir(year_dir: Path) -> None:
    if year_dir.exists():
        overwrite = ask_yes_no(
            f"{year_dir} already exists. Continue and overwrite the scaffolding "
            f"files this script writes inside it (never manifest.yaml, "
            f"strings-manifest.tex, or figures/)?",
            default=False,
        )
        if not overwrite:
            raise SystemExit("Aborted -- nothing written.")


# ============================================================
# Orchestration: standard theory/experiment shape
# ============================================================
def generate_shape_scaffold(
    year_dir: Path, calendar_year: str, shape: Shape,
    *, grades: list, languages: list[str], instructions: bool, wants_answers: bool,
) -> None:
    year_dir = year_dir.resolve()
    comp, subcomp = validate_base_dir(year_dir.parent)
    year_name = year_dir.name

    theory_groups = theory_problem_folders(shape)
    soljanka_indices = {i for i, g in enumerate(theory_groups) if len(g) > 1}
    experiment_folders = experiment_problem_folders(shape)
    experiment_groups = [[f] for f in experiment_folders]

    print(f"Scaffolding {year_dir}")
    print(f"  theory={shape.theory}   experiment={shape.experiment}")
    print(f"  grades: {grades}   languages: {languages}   instructions: {instructions}   answer sheets: {wants_answers}")

    missing_competition_files: set[str] = set()
    tours = ["theory"] + (["experiment"] if shape.experiment else [])

    for grade in grades:
        grade_dir = year_dir / str(grade)
        (grade_dir / "figures").mkdir(parents=True, exist_ok=True)

        for lang in languages:
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
                instructions=instructions, tour="theory", **common))
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
                    instructions=instructions, tour="experiment", **common))
                write_file(lang_dir / "experiment_sol.tex", render_solutions_doc(
                    groups=experiment_groups, soljanka_indices=set(), tour="experiment", **common))
                write_file(lang_dir / "experiment_marking.tex", render_marking_doc(
                    groups=experiment_groups, tour="experiment", **common))
                if wants_answers:
                    write_file(lang_dir / "experiment_answer.tex", render_answer_doc(
                        groups=experiment_groups, soljanka_indices=set(), tour="experiment", **common))

            missing_competition_files |= check_competition_level_files(
                comp, subcomp, lang, instructions, tours)

    print()
    print("Done. Still needed before this actually compiles:")
    print(f"  - {year_dir / 'manifest.yaml'} (this year's real dates/city)")
    print(f"  - then run: python process-strings.py {year_dir}")
    print(f"    (creates/completes strings-competition.tex and strings-manifest.tex")
    print(f"    from config.yaml/manifest.yaml, and reports anything it can't derive)")
    if missing_competition_files:
        print()
        print("  These family-level files (shared by every year) don't exist yet:")
        for f in sorted(missing_competition_files):
            print(f"    - {f}")


# ============================================================
# Orchestration: bare tour1/tour2/.../tourN shape (custom only)
# ============================================================
def generate_tour_folders_scaffold(
    year_dir: Path, grades: list, languages: list[str], num_tours: int,
) -> None:
    year_dir = year_dir.resolve()
    validate_base_dir(year_dir.parent)

    print(f"Scaffolding {year_dir}")
    print(f"  grades: {grades}   languages: {languages}   tours: {num_tours}")

    for grade in grades:
        grade_dir = year_dir / str(grade)
        (grade_dir / "figures").mkdir(parents=True, exist_ok=True)

        for lang in languages:
            lang_dir = grade_dir / str(lang)
            write_file(lang_dir / ".latexmkrc", render_latexmkrc())
            for i in range(1, num_tours + 1):
                (lang_dir / f"tour{i}").mkdir(parents=True, exist_ok=True)

    print()
    print("Done. This is a bare scaffold: tour folders only, no problem stubs and")
    print("no root documents -- a custom tour1/tour2/... layout isn't assumed to fit")
    print("the theory/experiment document templates, so you write those yourself.")


# ============================================================
# Interactive wizard
# ============================================================
def main() -> None:
    print("scaffolding.py -- interactive competition-year scaffolder")
    print()

    family = choose("Which olympiad format is this?", [
        ("respa", "respa"),
        ("respa_junior", "respa_junior"),
        ("custom", "custom (a new competition family)"),
    ])

    if family in ("respa", "respa_junior"):
        stage_options = [s for s in ("raion", "oblast", "final") if (family, s) in SHAPE_BY_PATH]
        subcomp = choose(f"Which stage of {family}?", [(s, s) for s in stage_options])
        comp = family
    else:
        comp = ask_foldername("Competition family folder name under competitions/ (e.g. otbor_izho): ")
        subcomp = ask_foldername("Stage/sub-competition folder name (e.g. final): ")

    start_year = ask_start_year()
    year_name = f"{start_year}-{(start_year + 1) % 100:02d}"
    year_dir = COMPETITIONS_ROOT / comp / subcomp / year_name
    print(f"-> folder: competitions/{comp}/{subcomp}/{year_name}")
    confirm_year_dir(year_dir)

    if family in ("respa", "respa_junior"):
        shape = SHAPES[SHAPE_BY_PATH[(comp, subcomp)]]
        defaults = FAMILY_DEFAULTS[family]
        first_half = (comp, subcomp) in FIRST_HALF_YEAR
        calendar_year = str(start_year if first_half else start_year + 1)
        wants_answers = (comp, subcomp) in HAS_ANSWER_SHEETS

        generate_shape_scaffold(
            year_dir, calendar_year, shape,
            grades=defaults["grades"], languages=defaults["languages"],
            instructions=defaults["instructions"], wants_answers=wants_answers,
        )
        return

    first_half = ask_yes_no(
        "Is this stage held in the first half of the academic year (autumn, "
        "before New Year)? Answer no if it runs from January onward.",
        default=False,
    )
    calendar_year = str(start_year if first_half else start_year + 1)

    grades = ask_list("Grades, comma-separated (e.g. 9,10,11): ")
    languages = ask_list("Language codes, comma-separated (e.g. ru,kz): ")

    tour_format = choose("Tour format?", [
        ("standard", "theory/experiment (standard)"),
        ("custom_tours", "custom tour1/tour2/.../tourN folders"),
    ])

    if tour_format == "custom_tours":
        n_tours = ask_int("How many tours (max 20)? ", 1, 20)
        generate_tour_folders_scaffold(year_dir, grades, languages, n_tours)
        return

    instructions = ask_yes_no("Include an instructions page per tour?", default=True)
    wants_answers = ask_yes_no(
        "Include answer sheets (answer.tex per problem, plus "
        "theory_answer.tex/experiment_answer.tex)?", default=False)

    n_theory = ask_int("How many theory problems (T1, T2, ...)? ", 1, 20)
    theory_shape = []
    for i in range(1, n_theory + 1):
        parts = ask_int(
            f"  T{i}: enter 0 or 1 for a plain problem, or the number of "
            f"sub-parts (e.g. 3 for T{i}A/T{i}B/T{i}C) if it's a солянка: ",
            0, 26)
        theory_shape.append(parts)
    n_experiment = ask_int(
        "How many experiment problems? Enter 0 for no experiment tour at all: ", 0, 20)

    shape = Shape(theory=theory_shape, experiment=n_experiment)
    generate_shape_scaffold(
        year_dir, calendar_year, shape,
        grades=grades, languages=languages,
        instructions=instructions, wants_answers=wants_answers,
    )


if __name__ == "__main__":
    main()
