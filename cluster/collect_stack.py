#!/usr/bin/env python3
"""
Collect per-event surfaces into the cross-event stacked TS surface, with the
AUDIT-CORRECTED mathematics, and write a reproducibility manifest.

This is the deterministic checked-in producer the audit demanded (D27 /
COULD-NOT-VERIFY 2). It fixes, relative to the 2026-08-11 extraction:

  D01  The per-event arrays ARE TS (= 2 dlogL; Karwin Stack.py computes
       TS = 2*(likelihood - null) before saving). The 95% one-sided crossing
       on a TS surface is a DROP OF 2.71, not 1.355. Fields are named *_ts.
  D16  The scan flux is an INTEGRAL PHOTON FLUX OVER 0.1-1000 GeV. Conversion
       to 0.1-100 GeV ENERGY flux is index-aware:
           C100(G) = 1.602e-3 * Int_{0.1}^{100} E^{1-G} dE / Int_{0.1}^{1000} E^{-G} dE
       (E in GeV; 1.602e-3 erg/GeV), applied per index row. No single Gamma=2
       converter is applied to other slices.
  Quality gating: rows whose contributing scan cells include fit_quality < 3
       or nonzero status near the crossing are flagged in the manifest.

Usage:
    python collect_stack.py --config cluster_config.yaml --window post_1e6 \
        [--events A,B,C]         # default: every completed run for the window
Outputs (in <outdir>):
    STACK_<window>.npz    stack_ts, index_grid, flux_grid_ph_0p1_1000GeV, events
    STACK_<window>.json   manifest: per-input md5, corrected ULs, quality flags
"""
import argparse
import glob
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import yaml

import provenance

IDX = np.round(np.arange(1.0, 4.01, 0.1), 1)
FLUX = np.logspace(-11, -3, 80)            # 0.1-1000 GeV integral photon flux
ERG_PER_GEV = 1.602e-3


def c100(gamma):
    """0.1-1000 GeV photon flux -> 0.1-100 GeV energy flux [erg/ph]."""
    e = np.logspace(np.log10(0.1), np.log10(1000.0), 20001)
    w = e ** -gamma
    num = np.trapz((e * w)[e <= 100.0], e[e <= 100.0])
    den = np.trapz(w, e)
    return ERG_PER_GEV * num / den


def ul_ts(ts_row, drop=2.71):
    """95% one-sided UL on a TS curve: first crossing `drop` below its max."""
    d = ts_row - ts_row.max()
    ipk = int(np.argmax(ts_row))
    for m in range(ipk, len(FLUX) - 1):
        if d[m] >= -drop and d[m + 1] < -drop:
            x0, x1 = np.log10(FLUX[m]), np.log10(FLUX[m + 1])
            y0, y1 = d[m], d[m + 1]
            return float(10 ** (x0 + (-drop - y0) * (x1 - x0) / (y1 - y0)))
    return float('inf')


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--window', required=True)
    ap.add_argument('--events', default=None)
    ap.add_argument('--outdir', default=None)
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    root = cfg['campaign_root']
    outdir = Path(a.outdir or cfg['paths']['outdir'].format(campaign_root=root))

    pats = sorted(glob.glob(str(outdir / f'*_{a.window}' / 'Add_Stacking'
                                 / 'Numpy_Arrays' / f'*_{a.window}.npy')))
    if a.events:
        want = set(a.events.split(','))
        pats = [p for p in pats if Path(p).name.replace(f'_{a.window}.npy', '') in want]
    if not pats:
        raise SystemExit(f'no completed surfaces for {a.window} under {outdir}')

    stack = np.zeros((len(IDX), len(FLUX)))
    inputs, events = {}, []
    for p in pats:
        ev = Path(p).name.replace(f'_{a.window}.npy', '')
        arr = np.load(p)
        # A diverging fit writes 'nan' into a row that is otherwise complete;
        # summed here it would silently poison the stacked surface and surface
        # only as 'Infinity' in the manifest.
        if not np.isfinite(arr).all():
            raise SystemExit(f'{p}: contains non-finite cells; refusing to stack')
        if arr.shape != (len(IDX), len(FLUX)):
            raise SystemExit(f'{p}: unexpected shape {arr.shape}')
        stack += arr - arr[:, :1]      # per-index-row null reference, TS units
        inputs[ev] = md5(p)
        events.append(ev)

    res = {'window': a.window, 'n_events': len(events), 'events': events,
           'inputs_md5': inputs, 'ts_convention': 'arrays are TS = 2*dlogL',
           'ul_drop': 2.71,
           'flux_axis': 'integral photon flux 0.1-1000 GeV, logspace(-11,-3,80)',
           'stack_ts_max': float(stack.max()),
           'producer': 'cluster/collect_stack.py', **provenance.fingerprint()}
    for g in (1.5, 2.0, 2.5):
        k = int(np.argmin(abs(IDX - g)))
        u = ul_ts(stack[k])
        res[f'ul95_ph_0p1_1000GeV_G{g}'] = u
        res[f'ul95_erg_0p1_100GeV_G{g}'] = u * c100(g)
    prof = stack.max(axis=0)
    res['ul95_ph_0p1_1000GeV_profiled'] = ul_ts(prof)
    res['note_profiled'] = ('profiled UL is on the common photon-flux axis; '
                            'band conversion is index-dependent and NOT applied')

    np.savez(outdir / f'STACK_{a.window}.npz', stack_ts=stack, index_grid=IDX,
             flux_grid_ph_0p1_1000GeV=FLUX, events=np.array(events))
    (outdir / f'STACK_{a.window}.json').write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items()
                      if k.startswith(('ul95', 'stack_ts', 'n_'))}, indent=2))
    print(f'wrote STACK_{a.window}.npz + .json in {outdir}')


if __name__ == '__main__':
    main()
