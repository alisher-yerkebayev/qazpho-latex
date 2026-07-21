# extract.py — parse an olympiad problem .tex file into problem.yaml
# Usage: python extract.py

import re
import sys
import shutil
from transliterate import slugify as slugify_ru
from slugify import slugify as slugify_en
import textwrap
from pathlib import Path
import yaml

# ── Helpers ──────────────────────────────────────────────────────────────────

def strip_latex_comments(latex_content: str) -> str:
    # 1. Match an unescaped % symbol and everything following it on that line
    comment_pattern = r'(?<!\\)%.*'
    
    # Use .rstrip() to clean the end of the line, keeping leading tabs/spaces intact
    clean_lines = [re.sub(comment_pattern, '', line).rstrip() for line in latex_content.splitlines()]
    joined_text = '\n'.join(clean_lines)
    
    # 2. Collapse excessive vertical empty space
    clean_text = re.sub(r'(\n\s*){3,}', '\n\n', joined_text)
    
    return clean_text

def strip_outer_braces(s: str) -> str:
    s = s.strip()
    if s.startswith('{') and s.endswith('}'):
        return s[1:-1].strip()
    return s

# ── Brace-balanced argument reader ───────────────────────────────────────────

def read_brace_arg(text: str, start: int) -> tuple[str, int]:
    i = start
    while i < len(text) and text[i] in ' \t\n\r':
        i += 1
        
    if i >= len(text):
        raise ValueError(f"Unexpected end of text while reading argument near position {start}")

    # Case 1: Braced argument
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
        
    # Case 2: Unbraced single-character argument
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

# ── Figure extraction ─────────────────────────────────────────────────────────

def parse_pic(text: str, pos: int) -> tuple[dict, int]:
    lines, pos = read_brace_arg(text, pos)
    align, pos = read_brace_arg(text, pos)
    vspace, pos = read_brace_arg(text, pos)
    width, pos = read_brace_arg(text, pos)
    path, pos = read_brace_arg(text, pos)
    caption, pos = read_optional_arg(text, pos)

    fig = {
        'command': 'pic',
        'original_path': path,
        'width': float(width),
        'align': align,
        'lines': int(lines),
    }
    if caption:
        fig['raw_caption'] = caption
    return fig, pos

def parse_cpic(text: str, pos: int) -> tuple[dict, int]:
    width, pos = read_brace_arg(text, pos)
    path, pos = read_brace_arg(text, pos)
    caption, pos = read_optional_arg(text, pos)

    fig = {
        'command': 'cpic',
        'original_path': path,
        'width': float(width),
    }
    if caption:
        fig['raw_caption'] = caption
    return fig, pos

def parse_cpics(text: str, pos: int) -> tuple[list[dict], int]:
    width1, pos = read_brace_arg(text, pos)
    path1, pos = read_brace_arg(text, pos)
    width2, pos = read_brace_arg(text, pos)
    path2, pos = read_brace_arg(text, pos)
    caption, pos = read_optional_arg(text, pos)

    fig1 = {
        'command': 'cpics',
        'original_path': path1,
        'width': float(width1),
    }
    fig2 = {
        'command': 'cpics',
        'original_path': path2,
        'width': float(width2),
    }
    
    if caption:
        fig1['raw_caption'] = caption
        fig2['raw_caption'] = caption
        
    return [fig1, fig2], pos

def resolve_image_path(base_dir: Path, img_path_str: str) -> Path | None:
    src = base_dir / img_path_str
    if src.is_file():
        return src
        
    raster_extensions = ['.png', '.jpg', '.jpeg']
    for ext in raster_extensions:
        candidate = base_dir / f"{img_path_str}{ext}"
        if candidate.is_file():
            return candidate
            
    pdf_candidate = base_dir / f"{img_path_str}.pdf"
    if pdf_candidate.is_file():
        return pdf_candidate
        
    return None

# ── Task item splitter ────────────────────────────────────────────────────────

def split_task_items(task_body: str) -> list[str]:
    items = []
    parts = re.split(r'\\item', task_body)
    for part in parts:
        part = part.strip()
        if part:
            items.append(part)
    return items

# ── Part / task block scanner ─────────────────────────────────────────────────

BLOCK_RE = re.compile(
    r'(\\part\s*\{)'                  # group 1: \part{
    r'|(\\begin\s*\{task\})'          # group 2: \begin{task}
    r'|(\\pic(?![a-zA-Z]))'           # group 3: \pic
    r'|(\\cpic(?![a-zA-Z]))'          # group 4: \cpic
    r'|(\\cpics(?![a-zA-Z]))'         # group 5: \cpics
    r'|(\\physeq\s*[\[{])',           # group 6: \physeq
    re.DOTALL
)

def extract_environment(text: str, env: str, start: int) -> tuple[str, int]:
    open_pat = re.compile(r'\\begin\s*\{' + re.escape(env) + r'\}')
    close_pat = re.compile(r'\\end\s*\{' + re.escape(env) + r'\}')
    depth = 1
    i = start
    while i < len(text):
        om = open_pat.search(text, i)
        cm = close_pat.search(text, i)
        if cm is None:
            raise ValueError(f"Unmatched \\begin{{{env}}}")
        if om and om.start() < cm.start():
            depth += 1
            i = om.end()
        else:
            depth -= 1
            if depth == 0:
                return text[start:cm.start()].strip(), cm.end()
            i = cm.end()
    raise ValueError(f"Unmatched \\begin{{{env}}}")

# ── Top-level problem body parser ─────────────────────────────────────────────

def parse_body(text: str) -> tuple[list, list]:
    parts = []
    all_figures = []
    current_part = {'title': None, 'content': []}

    i = 0
    last_i = 0

    def flush_prose(start, end):
        chunk = text[start:end].strip()
        if chunk:
            current_part['content'].append({'type': 'prose', 'latex': chunk})

    for m in BLOCK_RE.finditer(text):
        flush_prose(last_i, m.start())

        if m.group(1):  # \part{
            parts.append(current_part)
            title, end = read_brace_arg(text, m.start() + len('\\part'))
            current_part = {'title': title, 'content': []}
            last_i = end

        elif m.group(2):  # \begin{task}
            body, end = extract_environment(text, 'task', m.end())
            items = split_task_items(body)
            current_part['content'].append({
                'type': 'tasks',
                'items': items,
            })
            last_i = end

        elif m.group(3):  # \pic
            fig, end = parse_pic(text, m.start() + len('\\pic'))
            fig['id'] = f"fig_{len(all_figures) + 1:02d}"
            all_figures.append(fig)
            current_part['content'].append({'type': 'figure', 'ref': fig['id']})
            last_i = end

        elif m.group(4):  # \cpic
            fig, end = parse_cpic(text, m.start() + len('\\cpic'))
            fig['id'] = f"fig_{len(all_figures) + 1:02d}"
            all_figures.append(fig)
            current_part['content'].append({'type': 'figure', 'ref': fig['id']})
            last_i = end

        elif m.group(5):  # \cpics
            figs, end = parse_cpics(text, m.start() + len('\\cpics'))
            refs = []
            for fig in figs:
                fig['id'] = f"fig_{len(all_figures) + 1:02d}"
                all_figures.append(fig)
                refs.append(fig['id'])
            current_part['content'].append({'type': 'figure_group', 'refs': refs})
            last_i = end

        elif m.group(6):  # \physeq
            current_part['content'].append({
                'type': 'physeq_placeholder',
                'offset': m.start(),
            })
            last_i = m.start()

    flush_prose(last_i, len(text))
    parts.append(current_part)
    return parts, all_figures

# ── Extractor helper function ─────────────────────────────────────────────────────────

def process_problem_body(title: str, points: float, slug: str, body: str, tex_path: Path, output_dir: Path, lang: str) -> None:
    parts, figures = parse_body(body)

    figures_dir = output_dir / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)

    figures_map = {}
    
    if figures:
        for fig in figures:
            src = resolve_image_path(tex_path.parent, fig['original_path'])
            
            if src:
                suffix = src.suffix
                dest_name = fig['id'] + suffix
                dest = figures_dir / dest_name
                
                shutil.copy2(src, dest)
                
                if suffix.lower() == '.pdf':
                    print(f"  NOTE: Found PDF figure ({src.name}). Multi-page support pending.", file=sys.stderr)
            else:
                print(f"  WARNING: figure not found: {tex_path.parent / fig['original_path']}", file=sys.stderr)
                suffix = Path(fig['original_path']).suffix
                dest_name = fig['id'] + suffix

            entry = {k: v for k, v in fig.items() if k not in ('original_path', 'raw_caption')}
            entry['path'] = f"figures/{dest_name}"
            
            # Map caption to language-keyed dict
            if 'raw_caption' in fig:
                entry['caption'] = {lang: fig['raw_caption']}

            figures_map[fig['id']] = entry

    yaml_parts = []
    for p in parts:
        if p['title'] is None and not p['content']:
            continue
        part_dict = {}
        if p['title']:
            part_dict['title'] = {lang: p['title']}
        blocks = []
        for block in p['content']:
            if block['type'] == 'prose':
                blocks.append({'prose': {lang: block['latex']}})
            elif block['type'] == 'tasks':
                blocks.append({'tasks': [{lang: item} for item in block['items']]})
            elif block['type'] == 'figure':
                blocks.append({'figure': block['ref']})
            elif block['type'] == 'figure_group':
                blocks.append({'figure_group': block['refs']})
            elif block['type'] == 'physeq_placeholder':
                pass
        part_dict['blocks'] = blocks
        yaml_parts.append(part_dict)

    problem_yaml = {
        'meta': {
            'title': {lang: title},
            'points_total': points,
            'slug': slug,
            'source_file': str(tex_path.name),
            'language_extracted': lang,
        },
    }
    
    if figures_map:
        problem_yaml['figures'] = figures_map
    if yaml_parts:
        problem_yaml['parts'] = yaml_parts

    out_yaml = output_dir / 'problem.yaml'
    with open(out_yaml, 'w', encoding='utf-8') as f:
        yaml.dump(problem_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

# ── Slugifier ─────────────────────────────────

def get_slug(title: str, lang: str) -> str:
    if lang == 'kz':
        return slugify_en(title)
    elif lang == 'en':
        return slugify_en(title)
    else:
        return slugify_ru(title, language_code='ru')

# ── Main extractor ────────────────────────────────────────────────────────────

def extract(tex_path: Path, output_dir: Path, lang: str = 'ru') -> None:
    text = tex_path.read_text(encoding='utf-8')
    text = strip_latex_comments(text)

    pm = re.search(r'\\problem\s*\{', text)
    if not pm:
        raise ValueError("No \\problem{} command found")
    
    title, after_title = read_brace_arg(text, pm.start() + len('\\problem'))
    points, body_start = read_brace_arg(text, after_title)
    points = float(points)
    slug = get_slug(title, lang)
    body = text[body_start:].strip()

    sub_matches = list(re.finditer(r'\\subproblem\s*\{', body))

    if not sub_matches:
        process_problem_body(title, points, slug, body, tex_path, output_dir, lang)
        print(f"  -> Extracted standard problem: {title}")
    else:
        # Composite problem logic
        print(f"  -> Detected composite problem (Солянка) with {len(sub_matches)} subproblems.")
        subproblems_list = []

        for i, match in enumerate(sub_matches):
            sub_title, after_sub_title = read_brace_arg(body, match.start() + len('\\subproblem'))
            sub_points, sub_body_start = read_brace_arg(body, after_sub_title)
            sub_points = float(sub_points)
            
            # Generate the alphabetic prefix (a-, b-, c-, etc.) based on index
            prefix = f"{chr(97 + i)}-"
            sub_slug = f"{prefix}{get_slug(sub_title, lang)}"
            
            # Determine where the subproblem body ends
            if i + 1 < len(sub_matches):
                sub_body_end = sub_matches[i+1].start()
            else:
                sub_body_end = len(body)
                
            sub_body = body[sub_body_start:sub_body_end].strip()
            
            sub_output_dir = output_dir / sub_slug
            sub_output_dir.mkdir(parents=True, exist_ok=True)
            process_problem_body(sub_title, sub_points, sub_slug, sub_body, tex_path, sub_output_dir, lang)
            
            subproblems_list.append(sub_slug)
            print(f"    * Extracted subproblem: {sub_title}")

        composite_yaml = {
            'meta': {
                'title': {lang: title},
                'points_total': points,
                'slug': slug,
                'source_file': str(tex_path.name),
                'language_extracted': lang,
                'type': 'composite'
            },
            'subproblems': subproblems_list
        }
        
        out_yaml = output_dir / 'problem.yaml'
        with open(out_yaml, 'w', encoding='utf-8') as f:
            yaml.dump(composite_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

def main():
    if len(sys.argv) > 1:
        print("Usage: python extract.py")
        print("Please run without arguments and provide inputs interactively.")
        sys.exit(1)

    print("=== Problem Extractor ===")
    user_input = input("Enter parameters in the format: input.tex output_dir/ ru/kz/en\n> ").strip()
    
    parts = user_input.split()
    if len(parts) != 3:
        print("Error: Invalid input format. Expected exactly 3 arguments: <input.tex> <output_dir/> <lang>")
        sys.exit(1)

    tex_path = Path(parts[0])
    base_output_dir = Path(parts[1])
    lang = parts[2].lower()

    if lang not in {'ru', 'kz', 'en'}:
        print(f"Error: Invalid language '{lang}'. Restricted strictly to: ru, kz, en.")
        sys.exit(1)

    if not tex_path.exists():
        print(f"Error: File {tex_path} not found.")
        sys.exit(1)
        
    content = tex_path.read_text(encoding='utf-8')
    pm = re.search(r'\\problem\s*\{', content)
    if not pm:
        print("Error: No \\problem{} command found in file.")
        sys.exit(1)
    
    title, _ = read_brace_arg(content, pm.start() + len('\\problem'))
    slug = get_slug(title, lang)
    
    final_output_dir = base_output_dir / slug
    final_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting: {tex_path} (Language: {lang})")
    print(f"Target folder: {final_output_dir}")
    
    extract(tex_path, final_output_dir, lang)
    print("Done.")

if __name__ == '__main__':
    main()