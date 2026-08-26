#!/usr/bin/env python3
"""
process-strings.py
===================
Creates/completes the three tiers of \\OlympString{} string files for one
competition-year, and lints \\OlympString{}/\\SetOlympString{} usage across
that year's documents plus the shared class/layout files.

Tier                                                       Source
------------------------------------------------------------------------
competitions/<family>/strings-config.tex                   none (manual)
competitions/<family>/<stage>/strings-competition.tex      <family>/config.yaml
competitions/<family>/<stage>/<year>/strings-manifest.tex  <year>/manifest.yaml

strings-config.tex has no YAML source at all -- if it's missing, this
script seeds it from shared/example/strings-config.tex (a maintained
template) since there's nothing to generate it from. strings-competition.tex
and strings-manifest.tex each have a small fixed set of keys this script
knows how to derive from YAML; if the file already exists, only the keys
it's missing get appended -- existing declarations are never touched or
reordered.

\\OlympString{key} expands via a bare \\csname...\\endcsname, so an
undeclared key doesn't error at compile time -- it just silently vanishes
from the PDF. The lint this script always runs is the only thing that
catches that before it ships.

config.yaml / manifest.yaml fields this script actually reads
---------------------------------------------------------------
Everything else in those two files (organizer.*, tours.*.name.*, grades,
languages, has_instructions, has_experiment, ...) is NOT consumed here --
organizer/tourname/tournamelowercase are tier-1 (hand-written, no YAML
injection at all; a human copies the value in once and leaves a comment
pointing at the source field); grades/languages/has_instructions/
has_experiment aren't read by any current script (scaffolding.py hard-codes
its own FAMILY_DEFAULTS/SHAPES instead of reading config.yaml at all).

  \\SetOlympString key            <- YAML path (per <family>/<stage>)
  ------------------------------------------------------------------
  name                           <- config.yaml: name.<stage>.short.{ru,kz}
  name_full                      <- config.yaml: name.full.{ru,kz}            (same for every stage, NOT nested under <stage>)
  stage                          <- config.yaml: name.<stage>.stage.{ru,kz}
  duration                       <- config.yaml: tours.{theory,experiment}.duration.<stage>   (or a flat value shared by every stage, e.g. tours.experiment.problem_count)
  problemcount                   <- config.yaml: tours.theory.problem_count.<stage>
  problemcount_instructions      <- config.yaml: tours.{theory,experiment}.problem_count.<stage>

  city                           <- manifest.yaml: city.{ru,kz}
  eventdates                     <- manifest.yaml: dates.opening-ceremony.{day,month}, dates.closing-ceremony.{day,month}   (+ dates.year, via \\OlympYear{} at compile time, not read here)
  touronedate                    <- manifest.yaml: dates.first-tour.{day,month}
  tourtwodate                    <- manifest.yaml: dates.second-tour.{day,month}

Usage:
    python process-strings.py <year_dir> [--check-only]

    year_dir   e.g. competitions/respa/final/2025-26

Examples:
    python process-strings.py competitions/respa/final/2025-26
    python process-strings.py competitions/respa/oblast/2100-01 --check-only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


REPO_ROOT = Path(__file__).resolve().parent


# ============================================================
# Bounded linguistic tables
# ============================================================
# Everything below is hand-verified against the real, already-published
# competitions/respa/final/2025-26 strings files -- it is NOT a general
# Russian/Kazakh grammar engine. It covers the small integers that
# actually occur in this project's config.yaml files (tour durations in
# hours, problem counts). A genuinely new number just needs one more
# row added to the relevant table.

# RU month names, genitive case ("20 <месяца>"), 1-indexed.
_RU_MONTH_GENITIVE = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}
# KZ month names, plain form (used in "21 <month>, <year> жыл" -- touronedate/tourtwodate).
_KZ_MONTH_PLAIN = {
    1: "қаңтар", 2: "ақпан", 3: "наурыз", 4: "сәуір", 5: "мамыр", 6: "маусым",
    7: "шілде", 8: "тамыз", 9: "қыркүйек", 10: "қазан", 11: "қараша", 12: "желтоқсан",
}
# KZ month names, possessive/dated form (used in "20-25 <month>ы" -- eventdates).
_KZ_MONTH_POSSESSIVE = {
    1: "қаңтары", 2: "ақпаны", 3: "наурызы", 4: "сәуірі", 5: "мамыры", 6: "маусымы",
    7: "шілдесі", 8: "тамызы", 9: "қыркүйегі", 10: "қазаны", 11: "қарашасы", 12: "желтоқсаны",
}

# RU hour-word declension for "duration" (digit + declined noun, e.g. "5 часов").
_RU_HOUR_WORD = {1: "час", 2: "часа", 3: "часа", 4: "часа", 5: "часов", 6: "часов"}
_KZ_HOUR_WORD = "сағат"  # invariant regardless of count

# RU numeral, genitive case, for "problemcount_instructions" ("трёх задач").
_RU_NUMERAL_GENITIVE = {1: "одной", 2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти", 6: "шести"}
# Tour-name adjective, genitive singular (fem., agrees with "задачи") / genitive plural (agrees with "задач").
_RU_TOUR_ADJ = {
    "theory": {"sg": "теоретической", "pl": "теоретических"},
    "experiment": {"sg": "экспериментальной", "pl": "экспериментальных"},
}
_KZ_NUMERAL = {1: "бір", 2: "екі", 3: "үш", 4: "төрт", 5: "бес", 6: "алты"}


def _ru_duration_phrase(hours: int) -> str:
    return f"Продолжительность тура --- {hours} {_RU_HOUR_WORD[hours]}"


def _kz_duration_phrase(hours: int) -> str:
    return f"Турдың уақыты --- {hours} {_KZ_HOUR_WORD}"


def _ru_problemcount_phrase(n: int, tour: str) -> str:
    adj = _RU_TOUR_ADJ[tour]
    if n == 1:
        return f"{_RU_NUMERAL_GENITIVE[1]} {adj['sg']} задачи"
    return f"{_RU_NUMERAL_GENITIVE[n]} {adj['pl']} задач"


def _kz_problemcount_phrase(n: int, tour: str) -> str:
    # "тұрады" ("consists of") is part of the existing hand-written
    # experiment phrasing but not theory's -- replicated as observed.
    # experiment's problem_count is always 1 in every config.yaml seen
    # so far, so this branch never actually needs n != 1 in practice.
    phrase = f"{_KZ_NUMERAL[n]} есептен"
    return phrase + " тұрады" if tour == "experiment" else phrase


def _resolve_per_stage(value, stage: str):
    """config.yaml sometimes nests a value per-stage ({final: 5, oblast: 4})
    and sometimes gives one flat value shared by every stage (e.g.
    tours.experiment.problem_count: 1) -- handle both."""
    if isinstance(value, dict):
        return value.get(stage)
    return value


# ============================================================
# YAML loading
# ============================================================
def load_family_config(family: str) -> dict:
    path = REPO_ROOT / "competitions" / family / "config.yaml"
    if not path.is_file():
        raise SystemExit(f"{path} does not exist.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw.get(family, raw)


def load_manifest(year_dir: Path) -> dict:
    path = year_dir / "manifest.yaml"
    if not path.is_file():
        raise SystemExit(
            f"{path} does not exist -- strings-manifest.tex needs this "
            f"year's real dates/city before it can be generated."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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
    family, stage, year = rel_parts
    return family, stage, year


# ============================================================
# Tier-2 (strings-competition.tex) key registry
#
# Each render function takes (family, cfg, stage) where `cfg` is
# config.yaml's already-unwrapped per-family dict.
# ============================================================
def _tier2_name(family: str, cfg: dict, stage: str) -> str:
    # "short" is nested UNDER each stage (name.<stage>.short), not shared
    # across stages -- раion/oblast/final genuinely have different short
    # names ("Районная олимпиада" vs "Республиканская олимпиада"), unlike
    # "full" below, which is the same for every stage.
    short = cfg["name"][stage]["short"]
    return (
        "\\SetOlympString{name}{%\n"
        f"    \\ifOlympLangRu {short['ru']}\\fi%              % config.yaml: {family}.name.{stage}.short.ru\n"
        f"    \\ifOlympLangKz {short['kz']}\\fi%                % config.yaml: {family}.name.{stage}.short.kz\n"
        "}"
    )


def _tier2_name_full(family: str, cfg: dict, stage: str) -> str:
    # Unlike "short"/"stage", "full" is NOT nested per-stage -- it's the
    # olympiad program's one overarching official name, constant
    # regardless of which stage this is. Read it directly rather than
    # composing "\OlympString{name} + suffix" (name itself now varies
    # per stage, so that composition would silently produce the wrong
    # text for every stage except whichever one happens to match).
    full = cfg["name"]["full"]
    return (
        "\\SetOlympString{name_full}{%\n"
        f"    \\ifOlympLangRu {full['ru']}\\fi%       % config.yaml: {family}.name.full.ru\n"
        f"    \\ifOlympLangKz {full['kz']}\\fi%      % config.yaml: {family}.name.full.kz\n"
        "}"
    )


def _tier2_stage(family: str, cfg: dict, stage: str) -> str:
    stage_text = cfg["name"][stage]["stage"]
    return (
        "\\SetOlympString{stage}{%\n"
        f"    \\ifOlympLangRu {stage_text['ru']}\\fi%     % config.yaml: {family}.name.{stage}.stage.ru\n"
        f"    \\ifOlympLangKz {stage_text['kz']}\\fi%         % config.yaml: {family}.name.{stage}.stage.kz\n"
        "}"
    )


def _tier2_duration(family: str, cfg: dict, stage: str) -> str:
    tours = cfg.get("tours", {})
    theory_hours = _resolve_per_stage(tours.get("theory", {}).get("duration"), stage)
    exp_hours = _resolve_per_stage(tours.get("experiment", {}).get("duration"), stage)
    theory_line_ru = f"        \\ifOlympTheory {_ru_duration_phrase(theory_hours)}\\fi%\n" if theory_hours else "        \\ifOlympTheory\\fi%\n"
    exp_line_ru = f"        \\ifOlympExperiment {_ru_duration_phrase(exp_hours)}\\fi%\n" if exp_hours else "        \\ifOlympExperiment\\fi%\n"
    theory_line_kz = f"        \\ifOlympTheory {_kz_duration_phrase(theory_hours)}\\fi%\n" if theory_hours else "        \\ifOlympTheory\\fi%\n"
    exp_line_kz = f"        \\ifOlympExperiment {_kz_duration_phrase(exp_hours)}\\fi%\n" if exp_hours else "        \\ifOlympExperiment\\fi%\n"
    return (
        "\\SetOlympString{duration}{%                                  % config.yaml: "
        f"{family}.tours.{{theory,experiment}}.duration.{stage}\n"
        "    \\ifOlympLangRu%\n"
        f"{theory_line_ru}"
        f"{exp_line_ru}"
        "    \\fi%\n"
        "    \\ifOlympLangKz%\n"
        f"{theory_line_kz}"
        f"{exp_line_kz}"
        "    \\fi%\n"
        "}"
    )


def _tier2_problemcount(family: str, cfg: dict, stage: str) -> str:
    tours = cfg.get("tours", {})
    theory_n = _resolve_per_stage(tours.get("theory", {}).get("problem_count"), stage)
    return (
        f"% config.yaml: {family}.tours.theory.problem_count.{stage}\n"
        f"\\SetOlympString{{problemcount}}{{{theory_n}}}"
    )


def _tier2_problemcount_instructions(family: str, cfg: dict, stage: str) -> str:
    tours = cfg.get("tours", {})
    theory_n = _resolve_per_stage(tours.get("theory", {}).get("problem_count"), stage)
    exp_n = _resolve_per_stage(tours.get("experiment", {}).get("problem_count"), stage)
    lines = ["\\SetOlympString{problemcount_instructions}", "{%", "    \\ifOlympTheory%"]
    if theory_n:
        lines.append(f"        \\ifOlympLangRu {_ru_problemcount_phrase(theory_n, 'theory')}\\fi%")
        lines.append(f"        \\ifOlympLangKz {_kz_problemcount_phrase(theory_n, 'theory')}\\fi%")
    lines.append("    \\fi%")
    lines.append("    \\ifOlympExperiment%")
    if exp_n:
        lines.append(f"        \\ifOlympLangRu {_ru_problemcount_phrase(exp_n, 'experiment')}\\fi%")
        lines.append(f"        \\ifOlympLangKz {_kz_problemcount_phrase(exp_n, 'experiment')}\\fi%")
    lines.append("    \\fi%")
    lines.append("}")
    return "\n".join(lines)


TIER2_REGISTRY = {
    "name": _tier2_name,
    "name_full": _tier2_name_full,
    "stage": _tier2_stage,
    "duration": _tier2_duration,
    "problemcount": _tier2_problemcount,
    "problemcount_instructions": _tier2_problemcount_instructions,
}


# ============================================================
# Tier-3 (strings-manifest.tex) key registry
# ============================================================
def _tier3_city(manifest: dict, year_dir: Path) -> str:
    city = manifest["city"]
    suffix = "   % identical in both languages — no branching needed, actually" if city["ru"] == city["kz"] else ""
    return (
        "\\SetOlympString{city}{%\n"
        f"    \\ifOlympLangRu {city['ru']}\\fi%\n"
        f"    \\ifOlympLangKz {city['kz']}\\fi%\n"
        "}" + suffix
    )


def _tier3_eventdates(manifest: dict, year_dir: Path) -> str:
    dates = manifest["dates"]
    opening, closing = dates["opening-ceremony"], dates["closing-ceremony"]
    if opening["month"] != closing["month"]:
        raise SystemExit(
            f"{year_dir / 'manifest.yaml'}: opening-ceremony and "
            f"closing-ceremony are in different months -- eventdates' "
            f"template assumes both are in the same month. Extend "
            f"_tier3_eventdates() in process-strings.py to handle this."
        )
    month = opening["month"]
    return (
        "% manifest.yaml: dates.opening-ceremony="
        f"{opening['day']}, dates.closing-ceremony={closing['day']}, month={month}\n"
        "\\SetOlympString{eventdates}{%\n"
        f"    \\ifOlympLangRu {opening['day']}--{closing['day']} {_RU_MONTH_GENITIVE[month]} \\OlympYear{{}} года, г.~\\OlympString{{city}}\\fi%\n"
        f"    \\ifOlympLangKz \\OlympYear{{}} жылдың {opening['day']}-{closing['day']} {_KZ_MONTH_POSSESSIVE[month]}, \\OlympString{{city}}~қ-сы\\fi%\n"
        "}"
    )


def _tier3_touronedate(manifest: dict, year_dir: Path) -> str:
    d = manifest["dates"]["first-tour"]
    return (
        f"% manifest.yaml: dates.first-tour={d['day']}, month={d['month']}\n"
        "\\SetOlympString{touronedate}{%\n"
        f"    \\ifOlympLangRu {d['day']} {_RU_MONTH_GENITIVE[d['month']]} \\OlympYear{{}} года\\fi%\n"
        f"    \\ifOlympLangKz {d['day']} {_KZ_MONTH_PLAIN[d['month']]}, \\OlympYear{{}} жыл\\fi%\n"
        "}"
    )


def _tier3_tourtwodate(manifest: dict, year_dir: Path) -> str:
    d = manifest["dates"]["second-tour"]
    return (
        f"% manifest.yaml: dates.second-tour={d['day']}, month={d['month']}\n"
        "\\SetOlympString{tourtwodate}{%\n"
        f"    \\ifOlympLangRu {d['day']} {_RU_MONTH_GENITIVE[d['month']]} \\OlympYear{{}} года\\fi%\n"
        f"    \\ifOlympLangKz {d['day']} {_KZ_MONTH_PLAIN[d['month']]}, \\OlympYear{{}} жыл\\fi%\n"
        "}"
    )


TIER3_REGISTRY = {
    "city": _tier3_city,
    "eventdates": _tier3_eventdates,
    "touronedate": _tier3_touronedate,
    "tourtwodate": _tier3_tourtwodate,
}


# ============================================================
# File I/O helpers
# ============================================================
def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


_DECL_RE = re.compile(r"\\SetOlympString\{(\w+)\}")


def _strip_comment(line: str) -> str:
    """Truncate a line at its first unescaped '%' (LaTeX comment start),
    so example syntax in doc comments (e.g. "\\OlympString{key}") doesn't
    get mistaken for a real usage/declaration."""
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


def declared_keys(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    lines = (_strip_comment(l) for l in path.read_text(encoding="utf-8").splitlines())
    return set(_DECL_RE.findall("\n".join(lines)))


def create_or_append_tier(path: Path, registry: dict, *render_args) -> list[str]:
    """Returns the list of keys actually written (created fresh or appended)."""
    existing = declared_keys(path)
    missing = [k for k in registry if k not in existing]
    if not missing:
        return []
    blocks = [registry[k](*render_args) for k in missing]
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + "\n".join(blocks) + "\n"
        write_file(path, text)
    else:
        write_file(path, "\n".join(blocks) + "\n")
    return missing


def ensure_tier1(family: str) -> bool:
    """Returns True if strings-config.tex was just created."""
    path = REPO_ROOT / "competitions" / family / "strings-config.tex"
    if path.is_file():
        return False
    template = REPO_ROOT / "shared" / "example" / "strings-config.tex"
    write_file(path, template.read_text(encoding="utf-8"))
    return True


# ============================================================
# Lint: \OlympString{}/\OlympStringFallback{} usage vs \SetOlympString{} declarations
# ============================================================
_USAGE_RE = re.compile(r"\\OlympString(?:Fallback)?\{(\w+)\}")


def scan_usages(paths: list[Path]) -> dict[str, list[tuple[Path, int]]]:
    """key -> list of (file, line_number) usage sites."""
    usages: dict[str, list[tuple[Path, int]]] = {}
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for lineno, line in enumerate(lines, start=1):
            for key in _USAGE_RE.findall(_strip_comment(line)):
                usages.setdefault(key, []).append((path, lineno))
    return usages


def competition_tex_files(year_dir: Path, family_dir: Path) -> list[Path]:
    """Every .tex file this year's documents can actually \\input: the
    year tree itself, plus the family-level files every year's root
    documents pull in (title_<lang>.tex, instructions/) -- those live
    one level above the year folder, not inside it."""
    files = [p for p in year_dir.rglob("*.tex") if "build" not in p.relative_to(year_dir).parts]
    files += sorted(family_dir.glob("*.tex"))
    instructions_dir = family_dir / "instructions"
    if instructions_dir.is_dir():
        files += sorted(instructions_dir.rglob("*.tex"))
    return files


def run_lint(family: str, stage: str, year_dir: Path, tier1: Path, tier2: Path, tier3: Path) -> None:
    shared_files = [
        REPO_ROOT / "shared" / "olympiad.cls",
        REPO_ROOT / "shared" / "olympiad-layout.sty",
        REPO_ROOT / "shared" / "olympiad-marking.sty",
    ]
    family_dir = REPO_ROOT / "competitions" / family
    usages = scan_usages(shared_files + competition_tex_files(year_dir, family_dir))
    declared = declared_keys(tier1) | declared_keys(tier2) | declared_keys(tier3)

    undeclared = {k: v for k, v in usages.items() if k not in declared}
    unused = declared - set(usages)

    print()
    if undeclared:
        print(f"UNDECLARED (used but never \\SetOlympString'd -- {len(undeclared)} key(s)):")
        for key, sites in sorted(undeclared.items()):
            print(f"  {key}")
            for path, lineno in sites:
                print(f"      {path.relative_to(REPO_ROOT)}:{lineno}")
    else:
        print("UNDECLARED: none.")

    if unused:
        print(f"DECLARED BUT UNUSED (safe, informational -- {len(unused)} key(s)):")
        for key in sorted(unused):
            print(f"  {key}")
    else:
        print("DECLARED BUT UNUSED: none.")


# ============================================================
# Orchestration
# ============================================================
def process_year(year_dir: Path, check_only: bool) -> None:
    family, stage, year = parse_year_dir(year_dir)
    year_dir = year_dir.resolve()

    tier1 = REPO_ROOT / "competitions" / family / "strings-config.tex"
    tier2 = REPO_ROOT / "competitions" / family / stage / "strings-competition.tex"
    tier3 = year_dir / "strings-manifest.tex"

    print(f"Processing {year_dir.relative_to(REPO_ROOT)}  (family={family}, stage={stage}, year={year})")

    if check_only:
        print("--check-only: skipping creation/append, running lint only.")
        run_lint(family, stage, year_dir, tier1, tier2, tier3)
        return

    if ensure_tier1(family):
        print(f"  created {tier1.relative_to(REPO_ROOT)} from shared/example/strings-config.tex -- review its content, it's family-wide and shared by every stage/year.")

    family_cfg = load_family_config(family)
    added2 = create_or_append_tier(tier2, TIER2_REGISTRY, family, family_cfg, stage)
    if added2:
        print(f"  {tier2.relative_to(REPO_ROOT)}: added {', '.join(added2)}")
    else:
        print(f"  {tier2.relative_to(REPO_ROOT)}: already has every known key.")

    manifest_cfg = load_manifest(year_dir)
    added3 = create_or_append_tier(tier3, TIER3_REGISTRY, manifest_cfg, year_dir)
    if added3:
        print(f"  {tier3.relative_to(REPO_ROOT)}: added {', '.join(added3)}")
    else:
        print(f"  {tier3.relative_to(REPO_ROOT)}: already has every known key.")

    run_lint(family, stage, year_dir, tier1, tier2, tier3)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create/complete the 3-tier \\OlympString string files for one competition-year, and lint usage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("year_dir", type=Path, help="e.g. competitions/respa/final/2025-26")
    parser.add_argument("--check-only", action="store_true",
                         help="run the lint only; don't create or append anything")
    args = parser.parse_args()
    process_year(args.year_dir, args.check_only)


if __name__ == "__main__":
    main()
