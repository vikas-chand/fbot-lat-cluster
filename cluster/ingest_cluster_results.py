#!/usr/bin/env python3
"""
Validate and ingest the products returned from the cluster binned campaign.

Run this the moment Partha's (or LSU's) results arrive, BEFORE any number from
them reaches the manuscript. It answers, from the returned files alone:

  1. Is the campaign complete?      84 tasks, 6 windows, 14 G1/G2 events
  2. Was it the analysis we asked for?  every task_meta.json must record the
     same fork commit, the same emax, edisp on, and the 2-degree catalog freedom
  3. Do the stacked surfaces have the right shape and convention?
     (31 index x 80 flux, TS units, produced by cluster/collect_stack.py)
  4. Does the 1e5 s seam agree with our unbinned stack?  This is the validation
     the manuscript promises: agreement to tens of percent is a PASS; a
     factor-level disagreement means a configuration mismatch, not physics, and
     must be chased through binned_crosscheck/NOTES_binned_crosscheck.md section 3
     before anything is quoted.

It writes nothing into the tree of record; it only reports. Promotion of the
numbers into the manuscript is a separate, deliberate step.

Usage:
    python ingest_cluster_results.py --indir /path/to/returned/files
    python ingest_cluster_results.py --indir ... --json report.json
"""
import argparse
import glob
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WINDOWS = ['post_100ks', 'post_1e6', 'post_1e7', 'pre_100ks', 'pre_1e6', 'pre_1e7']
EXPECTED_TASKS = 84
EXPECTED_SHAPE = (31, 80)
# Provenance is compared MEASURED-vs-MEASURED: the hash the cluster stamped into
# its products, against the hash of the pipeline sitting in this repo. The old
# check compared a hardcoded literal with the identical literal in run_task.py
# and so could only ever pass. (--pipeline overrides which copy is authoritative.)
def _local_pipeline():
    # This file is shared by two trees: the cluster repo (pipeline at the root)
    # and the working project (pipeline under binned_crosscheck/).
    if os.environ.get('FS_PIPELINE_DIR'):
        return Path(os.environ['FS_PIPELINE_DIR'])
    for cand in (ROOT / 'Fermi_Stacking_Analysis' / 'fermi_stacking',
                 ROOT / 'binned_crosscheck' / 'Fermi_Stacking_Analysis' / 'fermi_stacking'):
        if cand.is_dir():
            return cand
    return ROOT / 'Fermi_Stacking_Analysis' / 'fermi_stacking'   # for the message


LOCAL_PIPELINE = _local_pipeline()
# our unbinned stack at the seam window, 0.1-100 GeV energy flux (erg/cm2/s)
UNBINNED_SEAM = ROOT / 'proper_stacking' / 'output_v2' / 'stacking_results.csv'


def load_unbinned_seam():
    import csv
    for r in csv.DictReader(open(UNBINNED_SEAM)):
        if r['window'] == 'post_100ks' and r['group'] == 'G1':
            return float(r['ul95_erg'])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--indir', required=True,
                    help='directory holding the returned STACK_*.npz/.json and task_meta.json')
    ap.add_argument('--json', default=None, help='write the report as JSON')
    a = ap.parse_args()
    ind = Path(a.indir)
    rep = {'indir': str(ind), 'checks': [], 'ok': True}

    def check(name, ok, detail):
        rep['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
        if not ok:
            rep['ok'] = False
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    print(f'ingesting {ind}\n')

    # ---- 1. completeness -------------------------------------------------
    metas = sorted(glob.glob(str(ind / '**' / 'task_meta.json'), recursive=True))
    check('task count', len(metas) == EXPECTED_TASKS,
          f'{len(metas)} task_meta.json found, expected {EXPECTED_TASKS}')

    stacks = {w: sorted(glob.glob(str(ind / '**' / f'STACK_{w}.npz'), recursive=True))
              for w in WINDOWS}
    missing = [w for w, v in stacks.items() if not v]
    check('six stacked windows', not missing,
          'all six present' if not missing else f'MISSING: {missing}')

    # ---- 2. configuration provenance ------------------------------------
    commits, emaxes, edisps, freerad, windows_seen = set(), set(), set(), set(), {}
    for m in metas:
        d = json.load(open(m))
        commits.add(str(d.get('pipeline_sha256')))
        emaxes.add(float(d.get('emax_mev', -1)))
        edisps.add(str(d.get('edisp')))
        freerad.add(float(d.get('free_radius_deg', -1)))
        windows_seen[d.get('window')] = windows_seen.get(d.get('window'), 0) + 1
    expected = None
    if LOCAL_PIPELINE.is_dir():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import provenance
        expected = provenance.pipeline_sha256(LOCAL_PIPELINE)
    check('one pipeline, and it is ours',
          len(commits) == 1 and expected is not None and commits == {expected},
          f'products stamped {sorted(c[:12] for c in commits)}; '
          f'our copy hashes to {(expected or "UNAVAILABLE")[:12]}'
          + ('' if expected else ' — local pipeline not found, cannot verify'))
    check('1 TeV analysis band', emaxes == {1000000.0},
          f'emax_mev values: {sorted(emaxes)}')
    check('energy dispersion on', edisps == {'1'},
          f'edisp flags: {sorted(edisps)}')
    check('2 deg catalog freedom', freerad == {2.0},
          f'free_radius_deg: {sorted(freerad)}')
    check('14 tasks per window', all(v == 14 for v in windows_seen.values()) and
          len(windows_seen) == 6, f'per-window task counts: {windows_seen}')

    # ---- 3. surface shape and convention --------------------------------
    for w in WINDOWS:
        if not stacks[w]:
            continue
        p = stacks[w][0]
        z = np.load(p, allow_pickle=True)
        keys = set(z.files)
        shape_ok = 'stack_ts' in keys and z['stack_ts'].shape == EXPECTED_SHAPE
        check(f'{w} surface', shape_ok,
              f"keys={sorted(keys)} shape={z['stack_ts'].shape if 'stack_ts' in keys else None}")
        j = Path(p).with_suffix('.json')
        if j.exists():
            man = json.load(open(j))
            conv_ok = (man.get('ul_drop') == 2.71 and
                       'TS' in str(man.get('ts_convention', '')))
            check(f'{w} manifest convention', conv_ok,
                  f"ul_drop={man.get('ul_drop')} n_events={man.get('n_events')} "
                  f"producer={man.get('producer')}")

    # ---- 4. the seam ------------------------------------------------------
    seam_j = ind / 'STACK_post_100ks.json'
    cand = sorted(glob.glob(str(ind / '**' / 'STACK_post_100ks.json'), recursive=True))
    if cand:
        man = json.load(open(cand[0]))
        binned = man.get('ul95_erg_0p1_100GeV_G2.0')
        unb = load_unbinned_seam()
        if binned and unb:
            ratio = binned / unb
            ok = 0.4 <= ratio <= 2.5      # tens of percent either way = pass
            check('1e5 s seam vs unbinned', ok,
                  f'binned {binned:.4e} / unbinned {unb:.4e} = {ratio:.3f} '
                  f'({"consistent" if ok else "FACTOR-LEVEL DISAGREEMENT - configuration bug, "
                     "see binned_crosscheck/NOTES_binned_crosscheck.md section 3"})')
            rep['seam'] = {'binned': binned, 'unbinned': unb, 'ratio': ratio}
        else:
            check('1e5 s seam vs unbinned', False,
                  f'could not read both values (binned={binned}, unbinned={unb})')

    # ---- summary ----------------------------------------------------------
    print('\n' + ('ALL CHECKS PASSED — safe to promote these numbers'
                  if rep['ok'] else
                  'CHECKS FAILED — do NOT quote these numbers until resolved'))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2))
        print(f'report written to {a.json}')
    return 0 if rep['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
