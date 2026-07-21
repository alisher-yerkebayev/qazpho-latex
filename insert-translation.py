# insert_translation.py — Merge two translated problem directories into one
# Usage: python insert_translation.py <folder1> <folder2>

import sys
import yaml
import shutil
import filecmp
from pathlib import Path

def check_structure(dir_path: Path) -> tuple[bool, str]:
    """Validates the structure to determine if it is standard, composite, or invalid."""
    yaml_path = dir_path / 'problem.yaml'
    if not yaml_path.exists():
        return False, f"Missing problem.yaml in {dir_path.name}"
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        
    is_composite = data.get('meta', {}).get('type') == 'composite'
    
    if not is_composite:
        # Standard: Should only contain problem.yaml and optionally a 'figures' directory
        for item in dir_path.iterdir():
            if item.is_dir() and item.name != 'figures':
                return False, f"Unexpected directory '{item.name}' in standard folder {dir_path.name}."
        return True, "standard"
    else:
        # Composite (Soljanka): Should contain multiple subdirectories matching the YAML subproblems
        subs = data.get('subproblems', [])
        if not subs:
            return False, f"Composite problem {dir_path.name} has an empty 'subproblems' list."
        for sub in subs:
            sub_dir = dir_path / sub
            if not sub_dir.is_dir():
                return False, f"Missing subproblem directory '{sub}' in {dir_path.name}."
            if not (sub_dir / 'problem.yaml').exists():
                return False, f"Missing problem.yaml in subproblem directory '{sub}'."
        return True, "composite"

def merge_standard(dir1: Path, dir2: Path, out_dir: Path, data1: dict, data2: dict, lang1: str, lang2: str, base_slug: str):
    """Core merge logic applied to a single standard problem (or subproblem)."""
    out_figures_dir = out_dir / 'figures'
    
    figs1 = data1.get('figures', {})
    figs2 = data2.get('figures', {})
    merged_figures = {}

    def handle_figure(ref1: str, ref2: str):
        f1 = dir1 / figs1[ref1]['path'] if ref1 in figs1 else None
        f2 = dir2 / figs2[ref2]['path'] if ref2 in figs2 else None

        cap1 = figs1.get(ref1, {}).get('caption', {})
        cap2 = figs2.get(ref2, {}).get('caption', {})
        merged_caption = {**cap1, **cap2}

        if (f1 and f1.is_file()) or (f2 and f2.is_file()):
            out_figures_dir.mkdir(parents=True, exist_ok=True)

        if f1 and f2 and f1.is_file() and f2.is_file() and filecmp.cmp(f1, f2, shallow=False):
            dest_name = f1.name
            dest_path = out_figures_dir / dest_name
            if not dest_path.exists():
                shutil.copy2(f1, dest_path)
            
            merged_fig = figs1[ref1].copy()
            merged_fig['path'] = f"figures/{dest_name}"
            if merged_caption:
                merged_fig['caption'] = merged_caption
            elif 'caption' in merged_fig:
                del merged_fig['caption']

            merged_figures[ref1] = merged_fig
            return ref1
            
        else:
            result_refs = {}
            if f1 and f1.is_file():
                ext1 = f1.suffix
                new_ref1 = f"{ref1}{lang1}"
                dest_name1 = f"{new_ref1}{ext1}"
                shutil.copy2(f1, out_figures_dir / dest_name1)
                
                merged_fig1 = figs1[ref1].copy()
                merged_fig1['path'] = f"figures/{dest_name1}"
                if cap1:
                    merged_fig1['caption'] = cap1
                merged_figures[new_ref1] = merged_fig1
                result_refs[lang1] = new_ref1
                
            if f2 and f2.is_file():
                ext2 = f2.suffix
                new_ref2 = f"{ref2}{lang2}"
                dest_name2 = f"{new_ref2}{ext2}"
                shutil.copy2(f2, out_figures_dir / dest_name2)
                
                merged_fig2 = figs2[ref2].copy()
                merged_fig2['path'] = f"figures/{dest_name2}"
                if cap2:
                    merged_fig2['caption'] = cap2
                merged_figures[new_ref2] = merged_fig2
                result_refs[lang2] = new_ref2
                
            return result_refs

    parts1 = data1.get('parts', [])
    parts2 = data2.get('parts', [])

    if len(parts1) != len(parts2):
        raise ValueError(f"Part count discrepancy: Folder 1 has {len(parts1)}, Folder 2 has {len(parts2)}.")

    merged_parts = []
    for p_idx, (p1, p2) in enumerate(zip(parts1, parts2)):
        merged_part = {}
        if 'title' in p1 or 'title' in p2:
            t1 = p1.get('title', {})
            t2 = p2.get('title', {})
            merged_part['title'] = {**t1, **t2}

        blocks1 = p1.get('blocks', [])
        blocks2 = p2.get('blocks', [])

        if len(blocks1) != len(blocks2):
            raise ValueError(f"Block discrepancy in Part {p_idx + 1}: Folder 1 has {len(blocks1)}, Folder 2 has {len(blocks2)}.")

        merged_blocks = []
        for b_idx, (b1, b2) in enumerate(zip(blocks1, blocks2)):
            type1 = list(b1.keys())[0]
            type2 = list(b2.keys())[0]

            if type1 != type2:
                raise ValueError(f"Block mismatch in Part {p_idx + 1}, Block {b_idx + 1}: ('{type1}' vs '{type2}').")

            if type1 == 'prose':
                merged_blocks.append({'prose': {**b1['prose'], **b2['prose']}})
            elif type1 == 'tasks':
                if len(b1['tasks']) != len(b2['tasks']):
                    raise ValueError(f"Task mismatch in Part {p_idx + 1}, Block {b_idx + 1}.")
                merged_tasks = [{**t1, **t2} for t1, t2 in zip(b1['tasks'], b2['tasks'])]
                merged_blocks.append({'tasks': merged_tasks})
            elif type1 == 'figure':
                merged_blocks.append({'figure': handle_figure(b1['figure'], b2['figure'])})
            elif type1 == 'figure_group':
                if len(b1['figure_group']) != len(b2['figure_group']):
                    raise ValueError(f"Figure group mismatch in Part {p_idx + 1}, Block {b_idx + 1}.")
                merged_blocks.append({'figure_group': [handle_figure(r1, r2) for r1, r2 in zip(b1['figure_group'], b2['figure_group'])]})
            elif type1 == 'physeq_placeholder':
                merged_blocks.append(b1)

        merged_part['blocks'] = merged_blocks
        merged_parts.append(merged_part)

    src_files = []
    src1 = data1['meta'].get('source_file')
    src2 = data2['meta'].get('source_file')
    if isinstance(src1, list): src_files.extend(src1)
    else: src_files.append(src1)
    if isinstance(src2, list): src_files.extend(src2)
    else: src_files.append(src2)
    
    merged_yaml = {
        'meta': {
            'title': {**data1['meta'].get('title', {}), **data2['meta'].get('title', {})},
            'points_total': data1['meta']['points_total'],
            'slug': base_slug,
            'source_file': list(set(src_files)),
            'languages': [lang1, lang2]
        },
    }
    
    if merged_figures:
        merged_yaml['figures'] = merged_figures
    if merged_parts:
        merged_yaml['parts'] = merged_parts

    with open(out_dir / 'problem.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(merged_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

def merge_directories(dir1: Path, dir2: Path):
    valid1, type1 = check_structure(dir1)
    if not valid1: raise ValueError(f"Directory 1 structure error: {type1}")
    
    valid2, type2 = check_structure(dir2)
    if not valid2: raise ValueError(f"Directory 2 structure error: {type2}")
    
    if type1 != type2:
        raise ValueError(f"Mismatched structures: '{dir1.name}' is {type1}, but '{dir2.name}' is {type2}.")

    with open(dir1 / 'problem.yaml', 'r', encoding='utf-8') as f: data1 = yaml.safe_load(f)
    with open(dir2 / 'problem.yaml', 'r', encoding='utf-8') as f: data2 = yaml.safe_load(f)
    
    lang1 = data1.get('meta', {}).get('language_extracted')
    lang2 = data2.get('meta', {}).get('language_extracted')
    
    if not lang1 or not lang2:
        raise ValueError("Missing 'language_extracted' in one or both meta blocks.")
    if lang1 == lang2:
        raise ValueError(f"Both folders marked as '{lang1}'. Cannot merge duplicates.")

    if lang2 == 'ru' and lang1 != 'ru':
        final_dir_name = dir2.name
        parent_dir = dir2.parent
        base_slug = data2['meta'].get('slug')
        base_is_dir2 = True
    else:
        final_dir_name = dir1.name
        parent_dir = dir1.parent
        base_slug = data1['meta'].get('slug')
        base_is_dir2 = False

    out_dir = parent_dir / f"{final_dir_name}_merged_tmp"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    try:
        if type1 == 'composite':
            subs1 = data1.get('subproblems', [])
            subs2 = data2.get('subproblems', [])
            
            if len(subs1) != len(subs2):
                raise ValueError(f"Subproblem count mismatch: {len(subs1)} vs {len(subs2)}.")

            final_subs = []
            for s1, s2 in zip(subs1, subs2):
                sub_dir1 = dir1 / s1
                sub_dir2 = dir2 / s2
                
                with open(sub_dir1 / 'problem.yaml', 'r', encoding='utf-8') as f: s_data1 = yaml.safe_load(f)
                with open(sub_dir2 / 'problem.yaml', 'r', encoding='utf-8') as f: s_data2 = yaml.safe_load(f)
                
                final_sub_slug = s_data2['meta'].get('slug') if base_is_dir2 else s_data1['meta'].get('slug')
                final_subs.append(final_sub_slug)
                
                sub_out = out_dir / final_sub_slug
                sub_out.mkdir()
                merge_standard(sub_dir1, sub_dir2, sub_out, s_data1, s_data2, lang1, lang2, final_sub_slug)
            
            # Combine root-level yaml data
            src_files = []
            src1 = data1['meta'].get('source_file')
            src2 = data2['meta'].get('source_file')
            if isinstance(src1, list): src_files.extend(src1)
            else: src_files.append(src1)
            if isinstance(src2, list): src_files.extend(src2)
            else: src_files.append(src2)

            merged_yaml = {
                'meta': {
                    'title': {**data1['meta'].get('title', {}), **data2['meta'].get('title', {})},
                    'points_total': data1['meta']['points_total'],
                    'slug': base_slug,
                    'source_file': list(set(src_files)),
                    'languages': [lang1, lang2],
                    'type': 'composite'
                },
                'subproblems': final_subs
            }
            with open(out_dir / 'problem.yaml', 'w', encoding='utf-8') as f:
                yaml.dump(merged_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
                
        else:
            merge_standard(dir1, dir2, out_dir, data1, data2, lang1, lang2, base_slug)

        shutil.rmtree(dir1)
        shutil.rmtree(dir2)
        
        final_dest = parent_dir / final_dir_name
        if final_dest.exists():
            shutil.rmtree(final_dest)
        out_dir.rename(final_dest)
        print(f"Successfully merged into {final_dest}/")

    except Exception as e:
        if out_dir.exists():
            shutil.rmtree(out_dir)
        raise e

def main():
    if len(sys.argv) != 3:
        print("Usage: python insert_translation.py <folder1> <folder2>")
        sys.exit(1)

    dir1 = Path(sys.argv[1])
    dir2 = Path(sys.argv[2])

    if not dir1.is_dir() or not dir2.is_dir():
        print("Error: Both inputs must be valid directories.", file=sys.stderr)
        sys.exit(1)

    try:
        print(f"Merging '{dir1.name}' and '{dir2.name}'...")
        merge_directories(dir1, dir2)
    except ValueError as e:
        print(f"\n[!] Merge failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()