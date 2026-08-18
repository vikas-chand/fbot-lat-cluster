#!/usr/bin/env python3
"""Write tasks.txt: one `EVENT WINDOW` line per pending task, from the catalog
and the scope in cluster_config.yaml. Completed tasks (combined .npy exists)
are omitted, so re-running after a partial campaign resubmits only what's left.
Usage: python make_manifest.py --config cluster_config.yaml [--include-b-tier]
"""
import argparse, csv, yaml
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--config', required=True)
ap.add_argument('--include-b-tier', action='store_true',
                help='extend scope to B1+B2 (timing-gated) events')
a = ap.parse_args()
cfg = yaml.safe_load(open(a.config))
root = cfg['campaign_root']
paths = {k: v.format(campaign_root=root) for k, v in cfg['paths'].items()}
tiers = set(cfg['scope']['tiers']) | ({'B1', 'B2'} if a.include_b_tier else set())
windows = cfg['scope']['windows']

tasks, skipped = [], 0
for r in csv.DictReader(open(paths['catalog'])):
    if r.get('tier') not in tiers or not r.get('t0_met'):
        continue
    mw = float(r['min_window_s']) if (r.get('min_window_s') or '').strip() else None
    for w in windows:
        dur = {'post_100ks': 1e5, 'pre_100ks': 1e5, 'post_1e6': 1e6,
               'pre_1e6': 1e6, 'post_1e7': 1e7, 'pre_1e7': 1e7}[w]
        if mw is None or dur < mw:      # timing gate
            continue
        done = Path(paths['outdir']) / f"{r['name']}_{w}" / 'Add_Stacking' / \
               'Numpy_Arrays' / f"{r['name']}_{w}.npy"
        if done.exists():
            skipped += 1; continue
        tasks.append(f"{r['name']} {w}")

Path('tasks.txt').write_text('\n'.join(tasks) + '\n')
print(f"tasks.txt: {len(tasks)} pending  ({skipped} already complete)")
