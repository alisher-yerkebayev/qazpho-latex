# ============================================
# FROZEN PROJECT --- WON'T BE USED FOR A WHILE
# ============================================
#
# extract-solution.py — Extract solution and marking scheme from LaTeX source
# Usage: python extract-solution.py <file.tex> <lang> <out_dir>

import sys
import re
import yaml
import shutil
from pathlib import Path

# ── Helpers ──────────────────────────────────────────────────────────────────

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

def slugify(text):
    text = text.lower()
    cyrillic_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'қ': 'q', 'ң': 'ng', 'ғ': 'gh', 'ұ': 'u', 'ү': 'u', 'ө': 'o', 'ә': 'a', 'і': 'i'
    }
    for k, v in cyrillic_map.items():
        text = text.replace(k, v)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')

# ── Brace-balanced argument reader ───────────────────────────────────────────

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

# ── Extraction Implementation ────────────────────────────────────────────────

def parse_solution_body(title, total_points, prefix_text, body_text, lang, tex_file, out_dir):
    blocks = []
    markings = []
    figures_dict = {}
    
    current_task_id = 1
    pos = 0
    eq_counter = 1
    fig_counter = 1
    
    current_prose = ""
    current_criteria = []
    
    task_subtotal = 0.0
    calculated_total = 0.0
    
    tex_dir = tex_file.parent
    figures_dir = out_dir / 'figures'
    
    def process_single_fig(fig_data):
        nonlocal fig_counter
        src = resolve_image_path(tex_dir, fig_data['original_path'])
        if src:
            figures_dir.mkdir(parents=True, exist_ok=True)
            new_name = f"{src.stem}_sol{src.suffix}"
            dest_path = figures_dir / new_name
            
            if not dest_path.exists():
                shutil.copy2(src, dest_path)
            
            fig_ref = f"fig_sol_{fig_counter}"
            fig_counter += 1
            
            entry = {k: v for k, v in fig_data.items() if k not in ('original_path', 'raw_caption', 'command')}
            entry['path'] = f"figures/{new_name}"
            if 'raw_caption' in fig_data:
                entry['caption'] = {lang: fig_data['raw_caption']}
                
            figures_dict[fig_ref] = entry
            return fig_ref
        else:
            print(f"Warning: Figure not found: {fig_data['original_path']}")
            return None

    while pos < len(body_text):
        match_eq = re.search(r'\\begin\{eq\}', body_text[pos:])
        match_crit = re.search(r'\\criterion', body_text[pos:])
        match_task = re.search(r'\\tasksol\b', body_text[pos:])
        match_pic = re.search(r'\\pic(?![a-zA-Z])', body_text[pos:])
        match_cpic = re.search(r'\\cpic(?![a-zA-Z])', body_text[pos:])
        match_cpics = re.search(r'\\cpics(?![a-zA-Z])', body_text[pos:])
        
        matches = []
        if match_eq: matches.append(('eq', match_eq.start() + pos, match_eq.end() + pos, match_eq))
        if match_crit: matches.append(('crit', match_crit.start() + pos, match_crit.end() + pos, match_crit))
        if match_task: matches.append(('task', match_task.start() + pos, match_task.end() + pos, match_task))
        if match_pic: matches.append(('pic', match_pic.start() + pos, match_pic.end() + pos, match_pic))
        if match_cpic: matches.append(('cpic', match_cpic.start() + pos, match_cpic.end() + pos, match_cpic))
        if match_cpics: matches.append(('cpics', match_cpics.start() + pos, match_cpics.end() + pos, match_cpics))
        
        if not matches:
            current_prose += body_text[pos:]
            break
            
        first_match = min(matches, key=lambda x: x[1])
        m_type, start, end, match_obj = first_match
        
        current_prose += body_text[pos:start]
        
        if m_type == 'task':
            if len(current_criteria) > 0:
                markings.append({
                    "id": current_task_id,
                    "subtotal": round(task_subtotal, 3),
                    "criteria": current_criteria
                })
                calculated_total += task_subtotal
                current_task_id += 1
                
            current_criteria = []
            task_subtotal = 0.0
            
            current_prose += "\\tasksol"
            pos = end
            
        elif m_type == 'eq':
            options_str, options_pos = read_optional_arg(body_text, end)
            options = parse_kv_options(options_str or "")
            
            end_idx = body_text.find(r'\end{eq}', options_pos)
            if end_idx == -1: end_idx = len(body_text)
            eq_body = body_text[options_pos:end_idx].strip()
            pos = end_idx + 8
            
            if current_prose.strip():
                blocks.append({"prose": {lang: current_prose.strip()}})
            current_prose = ""
            
            label_val = options.get('label', f'eq:{eq_counter:02d}')
            eq_counter += 1
            
            blocks.append({"equation": label_val})
            
            crit = {
                "type": "equation",
                "label": label_val,
            }
            if 'points' in options:
                crit['points'] = try_float(options['points'])
                
            crit['content'] = options.get('override', eq_body)
            
            if 'prefix' in options: crit['prefix'] = options['prefix']
            if 'tail' in options: crit['tail'] = options['tail']
            elif 'suffix' in options: crit['tail'] = options['suffix']
            
            if 'type' in options and options['type'] != 'common':
                if options['type'] in ['alternative', 'other']:
                    crit['type'] = 'alternative'
            
            if 'numpoints' in options and options['numpoints'] not in ['', '0', '0.0']:
                crit['numpoints'] = try_float(options['numpoints'])
                
            eff_points = 0.0
            if crit.get('type') != 'alternative':
                eff_points += get_point_value(crit.get('points'))
                eff_points += get_point_value(crit.get('numpoints'))
            task_subtotal += eff_points

            current_criteria.append(crit)
            
        elif m_type == 'crit':
            options_str, options_pos = read_optional_arg(body_text, end)
            options = parse_kv_options(options_str or "")
            
            crit_text, pos = read_brace_arg(body_text, options_pos)
            
            c_type = "text"
            if 'type' in options:
                if options['type'] == 'remark':
                    c_type = "remark"
                elif options['type'] == 'penalty':
                    c_type = "penalty"
                elif options['type'] == 'alternative':
                    c_type = "alternative"
                    
            crit = {
                "type": c_type,
            }
            if 'points' in options:
                crit['points'] = try_float(options['points'])
                
            crit['content'] = crit_text.strip()
            
            eff_points = 0.0
            if crit.get('type') not in ['penalty', 'alternative', 'remark']:
                eff_points += get_point_value(crit.get('points'))
            task_subtotal += eff_points
            
            current_criteria.append(crit)

        elif m_type in ['pic', 'cpic', 'cpics']:
            if current_prose.strip():
                blocks.append({"prose": {lang: current_prose.strip()}})
            current_prose = ""

            if m_type == 'pic':
                fig_data, pos = parse_pic(body_text, start + 4)
                ref = process_single_fig(fig_data)
                if ref:
                    blocks.append({"figure": ref})
                    
            elif m_type == 'cpic':
                fig_data, pos = parse_cpic(body_text, start + 5)
                ref = process_single_fig(fig_data)
                if ref:
                    blocks.append({"figure": ref})
                    
            elif m_type == 'cpics':
                fig_list, pos = parse_cpics(body_text, start + 6)
                refs = []
                for fig_data in fig_list:
                    ref = process_single_fig(fig_data)
                    if ref:
                        refs.append(ref)
                if refs:
                    blocks.append({"figure_group": refs})
            
    if current_prose.strip():
        blocks.append({"prose": {lang: current_prose.strip()}})
        
    if current_criteria:
        markings.append({
            "id": current_task_id,
            "subtotal": round(task_subtotal, 3),
            "criteria": current_criteria
        })
        calculated_total += task_subtotal
        
    markings.append({"total": total_points})

    print(f"  -> Calculated total: {round(calculated_total, 3)} vs Header: {total_points}")
    if abs(calculated_total - float(total_points)) > 0.001:
        print(f"  -> [!] WARNING: Subtotals ({round(calculated_total, 3)}) do not sum up to allocated points ({total_points}).")

    part_entry = {}
    if prefix_text and prefix_text.strip():
        part_entry['prefix'] = {lang: prefix_text.strip()}
    part_entry['blocks'] = blocks

    solution_yaml = {
        'meta': {
            'title': {lang: title},
            'points_total': total_points,
            'slug': slugify(title),
            'source_file': [tex_file.name],
            'languages': [lang]
        }
    }
    
    if figures_dict:
        solution_yaml['figures'] = figures_dict
        
    solution_yaml['parts'] = [part_entry]
    
    marking_yaml = {
        'marking': markings
    }

    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / 'solution.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(solution_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    with open(out_dir / 'marking.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(marking_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

def extract_solution(tex_content, lang, tex_file, out_dir):
    # Detect \subsolution directly or inside \solution
    sub_matches = list(re.finditer(r'\\subsolution\s*\{', tex_content))

    if not sub_matches:
        # Standard solution processing
        sol_idx = tex_content.find(r'\solution')
        if sol_idx == -1:
            print("Error: Neither \\subsolution nor \\solution command found.")
            return

        prefix_text = tex_content[:sol_idx].strip()
        b1_start = tex_content.find('{', sol_idx)
        title, b1_end = read_brace_arg(tex_content, b1_start)
        points_str, b2_end = read_brace_arg(tex_content, b1_end)
        body_text = tex_content[b2_end:]

        parse_solution_body(title, try_float(points_str), prefix_text, body_text, lang, tex_file, out_dir)
    else:
        # Soljanka subsolution logic (processes the single target subsolution block inside out_dir)
        first_sub = sub_matches[0]
        prefix_text = tex_content[:first_sub.start()].strip()
        
        # Parse the subsolution matching this invocation
        sub_title, after_sub_title = read_brace_arg(tex_content, first_sub.start() + len('\\subsolution'))
        sub_points_str, sub_body_start = read_brace_arg(tex_content, after_sub_title)
        
        sub_body_end = sub_matches[1].start() if len(sub_matches) > 1 else len(tex_content)
        sub_body = tex_content[sub_body_start:sub_body_end].strip()

        parse_solution_body(sub_title, try_float(sub_points_str), prefix_text, sub_body, lang, tex_file, out_dir)

def main():
    if len(sys.argv) != 4:
        print("Usage: python extract-solution.py <file.tex> <lang> <out_dir>")
        sys.exit(1)

    tex_file = Path(sys.argv[1])
    lang = sys.argv[2]
    out_dir = Path(sys.argv[3])

    if not tex_file.exists():
        print(f"Error: File '{tex_file}' not found.")
        sys.exit(1)

    with open(tex_file, 'r', encoding='utf-8') as f:
        content = f.read()

    extract_solution(content, lang, tex_file, out_dir)
    print(f"Successfully processed solution into {out_dir}/")

if __name__ == '__main__':
    main()