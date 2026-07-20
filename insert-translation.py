# insert_translation.py — Merge two translated problem directories into one
# Usage: python insert_translation.py <direction> <source_dir> <target_dir>
# Example: python insert_translation.py ru->kz ./problem_ru ./problem_kz

import sys
import yaml
import shutil
import filecmp
from pathlib import Path

def merge_problems(lang_src: str, lang_dst: str, dir_src: Path, dir_dst: Path):
    yaml_src_path = dir_src / 'problem.yaml'
    yaml_dst_path = dir_dst / 'problem.yaml'

    if not yaml_src_path.exists() or not yaml_dst_path.exists():
        print("Error: problem.yaml missing in one or both directories.", file=sys.stderr)
        sys.exit(1)

    with open(yaml_src_path, 'r', encoding='utf-8') as f:
        src_data = yaml.safe_load(f)
    with open(yaml_dst_path, 'r', encoding='utf-8') as f:
        dst_data = yaml.safe_load(f)

    # Prepare temporary output directory
    out_dir = dir_src.parent / f"{dir_src.name}_merged_tmp"
    out_figures_dir = out_dir / 'figures'
    out_figures_dir.mkdir(parents=True, exist_ok=True)

    src_figs = src_data.get('figures', {})
    dst_figs = dst_data.get('figures', {})

    merged_figures = {}
    merged_parts = []

    def handle_figure(ref_src: str, ref_dst: str):
        """Compares figures. Copies identical ones once, or renames distinct ones."""
        f_src = dir_src / src_figs[ref_src]['path']
        f_dst = dir_dst / dst_figs[ref_dst]['path']

        # If both exist and are identical files (binary comparison)
        if f_src.is_file() and f_dst.is_file() and filecmp.cmp(f_src, f_dst, shallow=False):
            dest_name = f_src.name
            dest_path = out_figures_dir / dest_name
            if not dest_path.exists():
                shutil.copy2(f_src, dest_path)
            
            merged_fig = src_figs[ref_src].copy()
            merged_fig['path'] = f"figures/{dest_name}"
            merged_figures[ref_src] = merged_fig
            return ref_src
            
        else:
            # Different files (or one is missing) -> apply language suffixes
            result_refs = {}
            
            if f_src.is_file():
                ext_src = f_src.suffix
                new_ref_src = f"{ref_src}{lang_src}"
                dest_name_src = f"{new_ref_src}{ext_src}"
                shutil.copy2(f_src, out_figures_dir / dest_name_src)
                
                merged_fig_src = src_figs[ref_src].copy()
                merged_fig_src['path'] = f"figures/{dest_name_src}"
                merged_figures[new_ref_src] = merged_fig_src
                result_refs[lang_src] = new_ref_src
                
            if f_dst.is_file():
                ext_dst = f_dst.suffix
                new_ref_dst = f"{ref_dst}{lang_dst}"
                dest_name_dst = f"{new_ref_dst}{ext_dst}"
                shutil.copy2(f_dst, out_figures_dir / dest_name_dst)
                
                merged_fig_dst = dst_figs[ref_dst].copy()
                merged_fig_dst['path'] = f"figures/{dest_name_dst}"
                merged_figures[new_ref_dst] = merged_fig_dst
                result_refs[lang_dst] = new_ref_dst
                
            return result_refs

    # ── Structural Comparison & Content Merger ──
    src_parts = src_data.get('parts', [])
    dst_parts = dst_data.get('parts', [])

    if len(src_parts) != len(dst_parts):
        shutil.rmtree(out_dir)
        raise ValueError(f"Discrepancy found: Source has {len(src_parts)} parts, Target has {len(dst_parts)} parts.")

    for p_idx, (p_src, p_dst) in enumerate(zip(src_parts, dst_parts)):
        merged_part = {}
        
        # Merge Part Titles
        if 'title' in p_src or 'title' in p_dst:
            t_src = p_src.get('title', {})
            t_dst = p_dst.get('title', {})
            merged_part['title'] = {**t_src, **t_dst}

        src_blocks = p_src.get('blocks', [])
        dst_blocks = p_dst.get('blocks', [])

        if len(src_blocks) != len(dst_blocks):
            shutil.rmtree(out_dir)
            raise ValueError(f"Discrepancy found in Part {p_idx + 1}: Source has {len(src_blocks)} blocks, Target has {len(dst_blocks)} blocks.")

        merged_blocks = []
        for b_idx, (b_src, b_dst) in enumerate(zip(src_blocks, dst_blocks)):
            src_type = list(b_src.keys())[0]
            dst_type = list(b_dst.keys())[0]

            if src_type != dst_type:
                shutil.rmtree(out_dir)
                raise ValueError(f"Discrepancy found in Part {p_idx + 1}, Block {b_idx + 1}: Type mismatch ('{src_type}' vs '{dst_type}').")

            if src_type == 'prose':
                merged_blocks.append({'prose': {**b_src['prose'], **b_dst['prose']}})
                
            elif src_type == 'tasks':
                if len(b_src['tasks']) != len(b_dst['tasks']):
                    shutil.rmtree(out_dir)
                    raise ValueError(f"Discrepancy found in Part {p_idx + 1}, Block {b_idx + 1} (Tasks): Item count mismatch.")
                
                merged_tasks = []
                for t_src, t_dst in zip(b_src['tasks'], b_dst['tasks']):
                    merged_tasks.append({**t_src, **t_dst})
                merged_blocks.append({'tasks': merged_tasks})
                
            elif src_type == 'figure':
                ref_src = b_src['figure']
                ref_dst = b_dst['figure']
                merged_blocks.append({'figure': handle_figure(ref_src, ref_dst)})
                
            elif src_type == 'figure_group':
                refs_src = b_src['figure_group']
                refs_dst = b_dst['figure_group']
                if len(refs_src) != len(refs_dst):
                    shutil.rmtree(out_dir)
                    raise ValueError(f"Discrepancy found in Part {p_idx + 1}, Block {b_idx + 1} (Figure Group): Count mismatch.")
                
                new_refs = []
                for r_s, r_d in zip(refs_src, refs_dst):
                    new_refs.append(handle_figure(r_s, r_d))
                merged_blocks.append({'figure_group': new_refs})
                
            elif src_type == 'physeq_placeholder':
                merged_blocks.append(b_src)

        merged_part['blocks'] = merged_blocks
        merged_parts.append(merged_part)

    # ── Finalize YAML ──
    merged_yaml = {
        'meta': {
            'title': {**src_data['meta'].get('title', {}), **dst_data['meta'].get('title', {})},
            'points_total': src_data['meta']['points_total'],
            'slug': src_data['meta']['slug'], # Retains original source sluggified title
            'source_file': [src_data['meta']['source_file'], dst_data['meta']['source_file']],
            'languages': [lang_src, lang_dst]
        },
    }
    
    if merged_figures:
        merged_yaml['figures'] = merged_figures
    if merged_parts:
        merged_yaml['parts'] = merged_parts

    out_yaml = out_dir / 'problem.yaml'
    with open(out_yaml, 'w', encoding='utf-8') as f:
        yaml.dump(merged_yaml, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    # ── Cleanup & Replace ──
    final_dir_name = dir_src.name
    shutil.rmtree(dir_src)
    shutil.rmtree(dir_dst)
    out_dir.rename(out_dir.parent / final_dir_name)
    
    print(f"Successfully merged into {final_dir_name}/")

def main():
    if len(sys.argv) != 4:
        print("Usage: python insert_translation.py <direction> <source_dir> <target_dir>")
        print("Example: python insert_translation.py ru->kz ./prob_ru ./prob_kz")
        sys.exit(1)

    direction = sys.argv[1]
    if "->" not in direction:
        print("Error: Direction must be formatted as 'lang1->lang2' (e.g., 'ru->kz').", file=sys.stderr)
        sys.exit(1)

    lang_src, lang_dst = direction.split('->')
    dir_src = Path(sys.argv[2])
    dir_dst = Path(sys.argv[3])

    if not dir_src.is_dir() or not dir_dst.is_dir():
        print("Error: Both source and target must be valid directories.", file=sys.stderr)
        sys.exit(1)

    try:
        print(f"Merging {dir_src.name} and {dir_dst.name}...")
        merge_problems(lang_src, lang_dst, dir_src, dir_dst)
    except ValueError as e:
        print(f"\n[!] Merge failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()