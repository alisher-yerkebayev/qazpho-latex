# extract-marking.py — Generate a camera-ready marking-scheme table
# (marking_ru.tex / marking_kz.tex) from an olympiad solution.tex source.
#
# Usage: python extract-marking.py <solution.tex> <out_dir> [ru|kz]
#   lang defaults to 'ru' if omitted.
# Writes <out_dir>/marking_<lang>.tex, meant to be \input at the very end
# of the solution — exactly what the banner in \showmarking (see
# olympiad-marking.sty) tells the author to do once the rough draft is
# ready to be finalised.
#
# This script is architecturally a sibling of extract-solution.py: it
# reuses the same brace/optional-argument readers, the same key=value
# option parser, and the same left-to-right state machine that walks
# \tasksol / \begin{eq}...\end{eq} / \criterion occurrences inside a
# \solution{...}{...} or \subsolution{...}{...} body. Where
# extract-solution.py freezes that walk into solution.yaml/marking.yaml
# for the website pipeline, this script freezes it into a raw LaTeX
# tabularx for print/PDF output.
#
# ── DESIGN NOTES (please review) ──────────────────────────────────────────
# 1. type=solutions vs type=marking is resolved AT LATEX COMPILE TIME, not
#    by this script. \documentclass never appears inside solution.tex, so
#    Python has no reliable way to know which type the final document will
#    use. Instead, this script always emits BOTH variants (column spec,
#    header row, the extra MP/A cells on every row, the mid-table
#    \pagebreak) and lets olympiad-marking.sty choose between them via
#    \ifOlympJury at compile time: \OlympJuryPick{sol}{mark} for
#    ordinary running text / table cells, and \OlympJuryBeginTable{sol
#    colspec}{mark colspec} specifically for opening the tabularx (in
#    place of \begin{tabularx}{\linewidth}{...}). These are NOT
#    interchangeable: a tabularx column-spec argument is scanned by
#    array/tabularx ONE TOKEN AT A TIME (\@mkpream/\@testpach), which
#    only ever expands a single token in isolation — a 2-argument macro
#    like \OlympJuryPick sitting there breaks, because TeX goes hunting
#    for its {sol}{mark} arguments in array's own scanning internals
#    instead of the braces actually written next to it (raising
#    "Illegal pream-token"). \OlympJuryBeginTable sidesteps this by
#    resolving \ifOlympJury...\fi to plain characters via \edef
#    BEFORE \begin{tabularx} is ever invoked, so array only ever sees a
#    literal, hand-written-looking colspec. See olympiad-marking.sty
#    for both macros.
# 2. Numbering: the task-number column (long format) still embeds the live
#    \OlympCurrentPrefix macro, resolved by LaTeX at compile time — a lone
#    .tex file has no way to know which problem number it will end up
#    being. Equation references, however, are emitted as bare
#    \eqref{<n>} calls (n = this file's own per-\solution/\subsolution
#    equation counter, exactly mirroring the real, live `equation`
#    counter). This relies on \eqref itself being redefined (see the
#    second snippet) to (a) prepend eq:\OlympCurrentPrefix. before
#    resolving, and (b) fall back to printing the bare number in
#    parentheses if that label is undefined — which is exactly what
#    happens when this same marking.tex is compiled standalone in a
#    type=marking document that never actually typesets the equations.
#    A custom label=... given to \eq bypasses this shorthand entirely and
#    is referenced with \OlympOldEqref{<label>} instead.
# 3. Kazakh strings in STRINGS['kz'] are best-effort placeholders (a few
#    terms, e.g. "формула", are commonly left as loanwords) — please check
#    them against whatever \OlympStringFallback already defines for
#    eq_formula / eq_numerical / marking_content / marking_points /
#    marking_total in your project, and edit STRINGS accordingly.
# 4. MP / A columns (type=marking only) are blank cells for hand-written
#    jury annotation. MP is per-criterion (one blank per row); the long
#    format's "second" MP-like column and the A column are per-task (one
#    merged blank spanning the task's rows, same multirow pattern as the
#    points subtotal). Adjust build_rows() if your jury's convention
#    differs.
# 5. Page-break heuristic: assumes ~50 characters of Russian/Kazakh text
#    per rendered line, sums that estimate across all rows, and — if it
#    exceeds PAGEBREAK_ROW_THRESHOLD — inserts, at the row/task boundary
#    nearest the true middle, an UNCONDITIONAL \end{tabularx} +
#    \OlympJuryBeginTable{...}{...} reopen, with \pagebreak and the
#    repeated marking-mode header each wrapped separately in their own
#    tiny \OlympJuryPick{}{...} fragment. In a type=solutions compile the
#    reopen is chosen with the SAME (solutions) colspec and neither
#    \pagebreak nor the header fire, so it's an invisible seam and the
#    table reads as whole. Never splits inside a multirow task group.
#    This is a rough estimate, as requested — the placement is still
#    subject to editorial review.
#    Do NOT fold the close+\pagebreak+reopen+header sequence back into
#    ONE string handed to a single \OlympJuryPick{}{...} call (as an
#    earlier version of this script did) -- \begin{tabularx}/\end{tabularx}
#    must be encountered directly in the main input stream, not read as
#    captured macro-argument text, or LaTeX raises "Extra }, or forgotten
#    $." / "Missing } inserted" depending on which \OlympJuryPick branch
#    ends up active. See the \OlympJuryBeginTable comment in
#    olympiad-marking.sty for the closely related bare-& note.
# 6. \subsolution ("soljanka") handling mirrors extract-solution.py
#    exactly: if any \subsolution{...} is present, only the *first* one is
#    processed (extract-solution.py's own find/first_sub logic never
#    looks past sub_matches[0] either).
#
# ── Helpers copied from extract-solution.py (kept byte-identical) ────────

import sys
import re
import math
from pathlib import Path


def try_float(val):
    try:
        return float(val)
    except ValueError:
        return val


def get_point_value(val):
    """Safely extracts point value, ignoring split points like '0.2/0.8'."""
    if val is None:
        return 0.0
    val_str = str(val).strip()
    if not val_str or '/' in val_str:
        return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_kv_options(options_str):
    """Parses comma-separated key=value pairs, ignoring commas inside {...}."""
    opts = {}
    if not options_str:
        return opts

    current_key = ""
    current_val = ""
    in_key = True
    depth = 0

    for char in options_str:
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1

        if char == '=' and in_key and depth == 0:
            in_key = False
            continue

        if char == ',' and depth == 0:
            opts[current_key.strip()] = current_val.strip()
            current_key = ""
            current_val = ""
            in_key = True
            continue

        if in_key:
            current_key += char
        else:
            current_val += char

    if current_key:
        opts[current_key.strip()] = current_val.strip()

    for k, v in opts.items():
        if v.startswith('{') and v.endswith('}'):
            opts[k] = v[1:-1].strip()

    return opts


def read_brace_arg(text: str, start: int) -> tuple[str, int]:
    i = start
    while i < len(text) and text[i] in ' \t\n\r':
        i += 1

    if i >= len(text):
        raise ValueError(f"Unexpected end of text while reading argument near position {start}")

    if text[i] == '{':
        depth = 0
        buf = []
        for j in range(i, len(text)):
            c = text[j]
            if c == '{':
                depth += 1
                if depth > 1:
                    buf.append(c)
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return ''.join(buf).strip(), j + 1
                else:
                    buf.append(c)
            else:
                buf.append(c)
        raise ValueError(f"Unmatched '{{' starting at position {i}")
    else:
        arg = text[i]
        return arg, i + 1


def read_optional_arg(text: str, start: int) -> tuple[str | None, int]:
    i = start
    while i < len(text) and text[i] in ' \t\n\r':
        i += 1

    if i < len(text) and text[i] == '[':
        depth = 0
        buf = []
        for j in range(i, len(text)):
            c = text[j]
            if c == '[':
                depth += 1
                if depth > 1:
                    buf.append(c)
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return ''.join(buf).strip(), j + 1
                else:
                    buf.append(c)
            else:
                buf.append(c)
    return None, start


# Figure macros (\pic, \cpic, \cpics) never contribute rows to the marking
# scheme, but they must still be parsed just far enough to know where they
# END, or the state machine below would misinterpret their arguments as
# stray text. These three are trimmed from extract-solution.py (only the
# resulting position is needed here, so the parsed field values are
# discarded).

def parse_pic(text: str, pos: int) -> tuple[dict, int]:
    lines, pos = read_brace_arg(text, pos)
    align, pos = read_brace_arg(text, pos)
    vspace, pos = read_brace_arg(text, pos)
    width, pos = read_brace_arg(text, pos)
    path, pos = read_brace_arg(text, pos)
    caption, pos = read_optional_arg(text, pos)
    return {}, pos


def parse_cpic(text: str, pos: int) -> tuple[dict, int]:
    width, pos = read_brace_arg(text, pos)
    path, pos = read_brace_arg(text, pos)
    caption, pos = read_optional_arg(text, pos)
    return {}, pos


def parse_cpics(text: str, pos: int) -> tuple[list, int]:
    width1, pos = read_brace_arg(text, pos)
    path1, pos = read_brace_arg(text, pos)
    width2, pos = read_brace_arg(text, pos)
    path2, pos = read_brace_arg(text, pos)
    caption, pos = read_optional_arg(text, pos)
    return [], pos


# ── Language-neutral strings ──────────────────────────────────────────────
# See DESIGN NOTE 3 above — please review the 'kz' row.

STRINGS = {
    'ru': {
        'content_header': 'Содержание',
        'points_header': 'Баллы',
        'total': 'Итого',
        'formula': 'Формула',
        'numerical': 'Численный ответ в',
    },
    'kz': {
        'content_header': 'Мазмұны',
        'points_header': 'Ұпайлар',
        'total': 'Барлығы',
        'formula': 'Формула',
        'numerical': 'Сандық жауабы',
    },
}


def fmt_points(value):
    """Round to 3 decimals for the internal check, display with a trimmed,
    minimum-one-decimal format (0.5, 1.0, 10.0, ...) — matches the style of
    the worked example (doc 3): '0.5', '1.0', '10.0'."""
    try:
        v = round(float(value), 3)
    except (TypeError, ValueError):
        return str(value)
    s = f"{v:.3f}".rstrip('0').rstrip('.')
    if '.' not in s:
        s += '.0'
    return s


def wrap_pick(sol_text, marking_text):
    """Wraps a (solutions-mode, marking-mode) pair of literal LaTeX chunks
    into a single \\OlympJuryPick{...}{...} call, resolved at compile time
    via \\ifOlympJury (see olympiad-marking.sty)."""
    return f"\\OlympJuryPick{{{sol_text}}}{{{marking_text}}}"


# ── type= classification (mirrors __olympm_settype_eq:n / _criterion:n) ──

def classify_eq_type(raw):
    raw = (raw or 'common').strip()
    if raw in ('', 'common'):
        return 'common'
    if raw in ('alternative', 'other'):
        return 'alt'
    print(f"Warning: type={raw} is not meaningful for \\eq "
          f"(only common/alternative/other are); treating as common.")
    return 'common'


def classify_criterion_type(raw):
    raw = (raw or 'text').strip()
    if raw in ('remark', 'penalty', 'alternative'):
        return 'alt', raw
    if raw in ('', 'text'):
        return 'common', 'text'
    print(f"Warning: type={raw} is not recognised by \\criterion "
          f"(only remark/penalty/alternative are); treating as plain text.")
    return 'common', 'text'


# ── Body parser: walks \tasksol / eq / \criterion, builds task groups ────

def parse_marking_body(body_text, lang):
    """Returns (tasks, calculated_total).

    tasks: list of {'id': int, 'rows': [row, ...], 'subtotal': float}
    Each row is one of:
      {'kind': 'eq', 'type': 'common'|'alt', 'prefix': str, 'ref': str,
       'body': str, 'suffix': str, 'points_raw': str|None}
      {'kind': 'eq_numeric', 'type': ..., 'ref': str, 'points_raw': str}
      {'kind': 'criterion', 'type': ..., 'subtype': str,
       'content': str, 'points_raw': str|None}

    'ref' is a ready-to-use LaTeX reference call: either \\eqref{<n>} (bare
    number, resolved live against \\OlympCurrentPrefix by the redefined
    \\eqref — see DESIGN NOTE 2) or \\OlympOldEqref{<custom label>} when the
    author gave an explicit label= option.
    """
    tasks = []
    current_task_id = 1
    current_rows = []
    task_subtotal = 0.0
    calculated_total = 0.0
    eq_counter = 1
    pos = 0

    while pos < len(body_text):
        m_eq = re.search(r'\\begin\{eq\}', body_text[pos:])
        m_crit = re.search(r'\\criterion', body_text[pos:])
        m_task = re.search(r'\\tasksol\b', body_text[pos:])
        m_pic = re.search(r'\\pic(?![a-zA-Z])', body_text[pos:])
        m_cpic = re.search(r'\\cpic(?![a-zA-Z])', body_text[pos:])
        m_cpics = re.search(r'\\cpics(?![a-zA-Z])', body_text[pos:])

        candidates = []
        for kind, m in (('eq', m_eq), ('crit', m_crit), ('task', m_task),
                        ('pic', m_pic), ('cpic', m_cpic), ('cpics', m_cpics)):
            if m:
                candidates.append((kind, m.start() + pos, m.end() + pos))
        if not candidates:
            break
        kind, start, end = min(candidates, key=lambda x: x[1])

        if kind == 'task':
            if current_rows:
                tasks.append({'id': current_task_id, 'rows': current_rows,
                               'subtotal': round(task_subtotal, 3)})
                calculated_total += task_subtotal
                current_task_id += 1
            current_rows = []
            task_subtotal = 0.0
            pos = end

        elif kind == 'eq':
            options_str, options_pos = read_optional_arg(body_text, end)
            options = parse_kv_options(options_str or "")
            end_idx = body_text.find(r'\end{eq}', options_pos)
            if end_idx == -1:
                end_idx = len(body_text)
            eq_body_raw = body_text[options_pos:end_idx].strip()
            pos = end_idx + len(r'\end{eq}')

            row_type = classify_eq_type(options.get('type'))
            custom_label = options.get('label')
            if custom_label:
                ref_tex = f"\\OlympOldEqref{{{custom_label}}}"
            else:
                ref_tex = f"\\eqref{{{eq_counter}}}"
            body_math = options.get('override', eq_body_raw)
            prefix_word = options.get('prefix') or STRINGS[lang]['formula']
            suffix = options.get('tail') or options.get('suffix') or ''
            points_raw = options.get('points')

            current_rows.append({
                'kind': 'eq', 'type': row_type, 'prefix': prefix_word,
                'ref': ref_tex, 'body': body_math, 'suffix': suffix,
                'points_raw': points_raw,
            })
            if row_type == 'common':
                task_subtotal += get_point_value(points_raw)

            numpoints_raw = options.get('numpoints')
            if numpoints_raw is not None and numpoints_raw not in ('', '0', '0.0'):
                current_rows.append({
                    'kind': 'eq_numeric', 'type': row_type,
                    'ref': ref_tex, 'points_raw': numpoints_raw,
                })
                if row_type == 'common':
                    task_subtotal += get_point_value(numpoints_raw)

            eq_counter += 1

        elif kind == 'crit':
            options_str, options_pos = read_optional_arg(body_text, end)
            options = parse_kv_options(options_str or "")
            crit_text, pos = read_brace_arg(body_text, options_pos)

            row_type, subtype = classify_criterion_type(options.get('type'))
            points_raw = options.get('points')

            current_rows.append({
                'kind': 'criterion', 'type': row_type, 'subtype': subtype,
                'content': crit_text.strip(), 'points_raw': points_raw,
            })
            if row_type == 'common':
                task_subtotal += get_point_value(points_raw)

        elif kind == 'pic':
            _, pos = parse_pic(body_text, start + 4)
        elif kind == 'cpic':
            _, pos = parse_cpic(body_text, start + 5)
        elif kind == 'cpics':
            _, pos = parse_cpics(body_text, start + 6)

    if current_rows:
        tasks.append({'id': current_task_id, 'rows': current_rows,
                       'subtotal': round(task_subtotal, 3)})
        calculated_total += task_subtotal

    return tasks, calculated_total


# ── Row rendering ──────────────────────────────────────────────────────────

def render_points_cell(points_raw, row_type, allow_blank):
    if points_raw is None or points_raw == '':
        text = '' if allow_blank else '\\textbf{?}'
    else:
        text = points_raw
    if row_type == 'alt' and text:
        text = f"\\textit{{{text}}}"
    return text


def render_content_and_points(row, lang):
    S = STRINGS[lang]
    if row['kind'] == 'eq':
        core = f"{row['ref']}: ${row['body']}$"
        if row['suffix']:
            core += f" {row['suffix']}"
        if row['type'] == 'alt':
            content = f"\\quad\\textit{{{row['prefix']}}} {core}"
        else:
            content = f"{row['prefix']} {core}"
        points = render_points_cell(row.get('points_raw'), row['type'], allow_blank=False)
    elif row['kind'] == 'eq_numeric':
        word = S['numerical']
        if row['type'] == 'alt':
            content = f"\\quad\\textit{{{word}}} {row['ref']}"
        else:
            content = f"{word} {row['ref']}"
        points = render_points_cell(row.get('points_raw'), row['type'], allow_blank=False)
    else:  # criterion
        if row['type'] == 'alt':
            content = f"\\quad\\textit{{{row['content']}}}"
        else:
            content = row['content']
        allow_blank = (row.get('subtype') == 'remark')
        points = render_points_cell(row.get('points_raw'), row['type'], allow_blank=allow_blank)
    return content, points


def build_rows(tasks, is_long, lang):
    """Builds fully-formatted physical table rows. Each row is wrapped
    WHOLESALE in \\OlympJuryPick{solutions-row}{marking-row} (mirroring
    build_header/build_total_row below), never split into a shared base
    plus a partial \\OlympJuryPick{}{ & & ...} tail for just the extra
    MP/A cells. The latter looks tempting (less duplication) but is
    actually broken TeX: a bare alignment-tab (&) sitting inside the
    FALSE branch of a conditional, in the middle of an otherwise-shared
    table row, desyncs \\halign's row/column bookkeeping and raises
    "Incomplete \\iffalse" once enough of the surrounding table has been
    read for it to surface -- reproducible with nothing but plain
    \\iffalse & \\fi inside a bare tabular row, no custom macros
    involved. \\OlympJuryPick itself is perfectly safe -- for CELL
    CONTENT, or wrapping an entire row/line as done here -- just never
    for a fragment that leaves a stray & in the skipped branch."""
    physical = []
    for task in tasks:
        n = len(task['rows'])
        for i, row in enumerate(task['rows']):
            content, points = render_content_and_points(row, lang)
            base_cells = []

            if is_long:
                if i == 0:
                    base_cells.append(f"\\multirow{{{n}}}{{*}}{{\\textbf{{\\OlympCurrentPrefix.{task['id']}}}}}")
                else:
                    base_cells.append("")

            base_cells.append(content)
            base_cells.append(points)

            if is_long:
                if i == 0:
                    base_cells.append(f"\\multirow{{{n}}}{{*}}{{\\textbf{{{fmt_points(task['subtotal'])}}}}}")
                else:
                    base_cells.append("")

            base = " & ".join(base_cells)

            if is_long:
                if i == 0:
                    marking_extra = f" & & \\multirow{{{n}}}{{*}}{{}} & \\multirow{{{n}}}{{*}}{{}}"
                else:
                    marking_extra = " & & & "
            else:
                marking_extra = " & & "

            is_last = (i == n - 1)
            if is_long:
                sep_sol = "\\hline" if is_last else "\\cline{2-3}"
                sep_mark = "\\hline" if is_last else "\\cline{2-3}\\cline{5-5}"
            else:
                sep_sol = sep_mark = "\\hline"

            sol_line = f"{base} \\\\ {sep_sol}"
            mark_line = f"{base}{marking_extra} \\\\ {sep_mark}"
            line = wrap_pick(sol_line, mark_line)
            physical.append({
                'tex': line,
                'lines_est': max(1, math.ceil(len(content) / 50)),
                # Safe pagebreak points: any row boundary in short form,
                # only end-of-task boundaries in long form (never split a
                # multirow group across a page break).
                'task_boundary': (not is_long) or is_last,
            })
    return physical


# ── Header / column-width tables (transcribed verbatim from spec; two
#    obvious typos in the long+ru+solutions spec string were fixed:
#    missing '{' after two '>' , and one stray trailing '}') ──────────────

COLSPECS = {
    ('short', 'solutions', 'ru'):
        r"|p{0.88\linewidth}|>{\centering\arraybackslash}p{0.08\linewidth}|",
    ('short', 'solutions', 'kz'):
        r"|p{0.862\linewidth}|>{\centering\arraybackslash}p{0.098\linewidth}|",
    ('short', 'marking', 'ru'):
        r"|p{0.66\linewidth}|>{\centering\arraybackslash}p{0.08\linewidth}|"
        r">{\centering\arraybackslash}p{0.06\linewidth}|>{\centering\arraybackslash}p{0.06\linewidth}|",
    ('short', 'marking', 'kz'):
        r"|p{0.655\linewidth}|>{\centering\arraybackslash}p{0.085\linewidth}|"
        r">{\centering\arraybackslash}p{0.06\linewidth}|>{\centering\arraybackslash}p{0.06\linewidth}|",
    ('long', 'solutions', 'ru'):
        r"|>{\centering\arraybackslash}p{0.065\linewidth}|>{\arraybackslash}p{0.74\linewidth}|"
        r">{\centering\arraybackslash}p{0.05\linewidth}|>{\centering\arraybackslash}p{0.045\linewidth}|",
    ('long', 'solutions', 'kz'):
        r"|>{\centering\arraybackslash}p{0.1\linewidth}|>{\arraybackslash}p{0.705\linewidth}|"
        r">{\centering\arraybackslash}p{0.045\linewidth}|>{\centering\arraybackslash}p{0.045\linewidth}|",
    ('long', 'marking', 'ru'):
        r"|>{\centering\arraybackslash}p{0.055\linewidth}|>{\arraybackslash}p{0.54\linewidth}|"
        r">{\centering\arraybackslash}p{0.04\linewidth}|>{\centering\arraybackslash}p{0.045\linewidth}|"
        r">{\centering\arraybackslash}p{0.04\linewidth}|>{\centering\arraybackslash}p{0.04\linewidth}|"
        r">{\centering\arraybackslash}p{0.04\linewidth}|",
    ('long', 'marking', 'kz'):
        r"|>{\centering\arraybackslash}p{0.088\linewidth}|>{\arraybackslash}p{0.502\linewidth}|"
        r">{\centering\arraybackslash}p{0.04\linewidth}|>{\centering\arraybackslash}p{0.045\linewidth}|"
        r">{\centering\arraybackslash}p{0.04\linewidth}|>{\centering\arraybackslash}p{0.04\linewidth}|"
        r">{\centering\arraybackslash}p{0.04\linewidth}|",
}


def get_colspec(size, kind, lang):
    return COLSPECS[(size, kind, lang)]


def build_header(is_marking, is_long, lang):
    S = STRINGS[lang]
    c, p = S['content_header'], S['points_header']
    if not is_long:
        if not is_marking:
            return f"\\multicolumn{{1}}{{|c|}}{{\\textbf{{{c}}}}} & \\textbf{{{p}}} \\\\ \\hline"
        return (f"\\multicolumn{{1}}{{|c|}}{{\\textbf{{{c}}}}} & \\textbf{{{p}}} & "
                f"\\textbf{{MP}} & \\textbf{{A}} \\\\ \\hline")
    if not is_marking:
        return (f"\\textbf{{\\textnumero}} & \\multicolumn{{1}}{{c|}}{{\\textbf{{{c}}}}} & "
                f"\\multicolumn{{2}}{{c|}}{{\\textbf{{{p}}}}} \\\\ \\hline")
    return (f"\\textbf{{\\textnumero}} & \\multicolumn{{1}}{{c|}}{{\\textbf{{{c}}}}} & "
            f"\\multicolumn{{2}}{{c|}}{{\\textbf{{{p}}}}} & "
            f"\\multicolumn{{2}}{{c|}}{{\\textbf{{MP}}}} & \\textbf{{A}}\\\\ \\hline")


def build_total_row(total_points, is_marking, is_long, lang):
    S = STRINGS[lang]
    total_str = fmt_points(total_points)
    if is_long:
        cells = [f"\\textbf{{{S['total']}}}", "", "", f"\\textbf{{{total_str}}}"]
        if is_marking:
            cells += ["", "", ""]
    else:
        cells = [f"\\textbf{{{S['total']}}}", f"\\textbf{{{total_str}}}"]
        if is_marking:
            cells += ["", ""]
    return " & ".join(cells) + " \\\\ \\hline"


# ── Pagebreak heuristic (always computed; only active when \ifOlympJury
#    is true at compile time — see wrap_pick() usage in generate_marking_tex) ─

PAGEBREAK_ROW_THRESHOLD = 36  # see DESIGN NOTE 5


def split_for_pagebreak(rows, threshold=PAGEBREAK_ROW_THRESHOLD):
    total = sum(r['lines_est'] for r in rows)
    if total <= threshold:
        return None
    target = total / 2.0
    cum = 0
    best_idx, best_diff = None, None
    for i, r in enumerate(rows):
        cum += r['lines_est']
        if r['task_boundary']:
            diff = abs(cum - target)
            if best_diff is None or diff < best_diff:
                best_diff, best_idx = diff, i
    if best_idx is None or best_idx == len(rows) - 1:
        return None
    return best_idx


# ── Top-level assembly ─────────────────────────────────────────────────────

def generate_marking_tex(tasks, total_points, is_long, lang):
    size = 'long' if is_long else 'short'

    colspec_sol = get_colspec(size, 'solutions', lang)
    colspec_mark = get_colspec(size, 'marking', lang)

    header_mark = build_header(True, is_long, lang)
    header = wrap_pick(build_header(False, is_long, lang), header_mark)

    rows = build_rows(tasks, is_long, lang)

    total_row = wrap_pick(build_total_row(total_points, False, is_long, lang),
                           build_total_row(total_points, True, is_long, lang))

    out = [
        "% Auto-generated by extract-marking.py -- do not edit by hand unless you know what to do.",
        "% Works for BOTH \\documentclass[...,type=solutions,...] and",
        "% [...,type=marking,...] compiles, chosen at compile time via",
        "% \\OlympJuryPick / \\OlympJuryBeginTable (see olympiad-marking.sty).",
        "% \\eqref{n} falls back to a plain '(n)' whenever the referenced",
        "% equation isn't actually typeset in the current document.",
        "",
        f"\\makegapedcells\\OlympJuryBeginTable{{{colspec_sol}}}{{{colspec_mark}}}",
        "\\hline",
        header,
    ]

    split_idx = split_for_pagebreak(rows)
    for i, r in enumerate(rows):
        out.append(r['tex'])
        if split_idx is not None and i == split_idx:
            # The close/reopen itself is UNCONDITIONAL (\OlympJuryBeginTable
            # picks the right colspec either way, so in a type=solutions
            # compile this is an invisible no-op seam); only \pagebreak and
            # the repeated header are marking-only, and each is its own
            # small \OlympJuryPick{}{...} fragment with no bare & in it.
            # Do NOT collapse this back into one \end{tabularx}\begin{...}
            # string handed to \OlympJuryPick as a single argument -- LaTeX's
            # \begin/\end need to be encountered directly in the main input
            # stream, not read as captured macro-argument text, or you get
            # "Extra }, or forgotten $." / "Missing } inserted" depending on
            # which branch is active. See olympiad-marking.sty.
            out.append(wrap_pick("", "\\pagebreak"))

    out.append(total_row)
    out.append("\\end{tabularx}")

    return "\n".join(out) + "\n"


# ── \solution / \subsolution block selection (mirrors extract_solution) ──

def find_target_block(content):
    sub_matches = list(re.finditer(r'\\subsolution\s*\{', content))

    if not sub_matches:
        sol_idx = content.find(r'\solution')
        if sol_idx == -1:
            print("Error: Neither \\subsolution nor \\solution command found.")
            return None, None, None
        b1_start = content.find('{', sol_idx)
        title, b1_end = read_brace_arg(content, b1_start)
        points_str, b2_end = read_brace_arg(content, b1_end)
        body = content[b2_end:]
        return title, try_float(points_str), body
    else:
        # Only the first \subsolution is processed, exactly like
        # extract-solution.py's own sub_matches[0]-based logic.
        first_sub = sub_matches[0]
        title, after_title = read_brace_arg(content, first_sub.start() + len('\\subsolution'))
        points_str, body_start = read_brace_arg(content, after_title)
        body_end = sub_matches[1].start() if len(sub_matches) > 1 else len(content)
        body = content[body_start:body_end].strip()
        return title, try_float(points_str), body


# ── main ────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) not in (3, 4):
        print("Usage: python extract-marking.py <file.tex> <out_dir> [ru|kz]")
        sys.exit(1)

    tex_file = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    lang = sys.argv[3].strip().lower() if len(sys.argv) == 4 else 'ru'
    if lang not in ('ru', 'kz'):
        print(f"Warning: unrecognized language '{lang}'; defaulting to 'ru'.")
        lang = 'ru'

    if not tex_file.exists():
        print(f"Error: File '{tex_file}' not found.")
        sys.exit(1)

    content = tex_file.read_text(encoding='utf-8')

    title, total_points, body = find_target_block(content)
    if body is None:
        sys.exit(1)

    tasksol_count = len(re.findall(r'\\tasksol\b', body))
    is_long = tasksol_count >= 2

    tasks, calculated_total = parse_marking_body(body, lang)

    print(f"  -> Calculated total: {round(calculated_total, 3)} vs Header: {total_points}")
    try:
        mismatch = abs(calculated_total - float(total_points)) > 0.001
    except (TypeError, ValueError):
        mismatch = False
    if mismatch:
        print(f"  -> [!] WARNING: Subtotals ({round(calculated_total, 3)}) "
              f"do not sum up to allocated points ({total_points}).")

    tex_out = generate_marking_tex(tasks, total_points, is_long, lang)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{tex_file.stem}_marking_{lang}.tex"
    with open(out_dir / out_name, 'w', encoding='utf-8') as f:
        f.write(tex_out)

    print(f"Detected: language={lang}, {'long (subtasks)' if is_long else 'short'} format "
          f"({tasksol_count} \\tasksol occurrence(s)); type=solutions/marking is "
          f"resolved at LaTeX compile time via \\OlympJuryPick.")
    print(f"Successfully processed marking scheme into {out_dir}/{out_name}")


if __name__ == '__main__':
    main()