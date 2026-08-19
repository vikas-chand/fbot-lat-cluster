#!/usr/bin/env python3
"""
Build the per-event FT1 cones from a LOCAL LAT weekly-data mirror, instead of
querying the FSSC.

Use this when the cluster already holds the LAT weekly photon files (most LAT
groups mirror them). It produces exactly the same per-event trees that
cluster/download_ft1_1tev.py would fetch, so run_task.py cannot tell the
difference and the D02 energy guard passes.

The selection replicates the FSSC query used for this campaign:
    radius 30 deg around the event position
    [t0 - 1e7 s, t0 + 1e7 s], clipped to the mission span
    100 MeV - 1000 GeV      <- the 1 TeV ceiling is REQUIRED: run_task.py
                               refuses to run a 1 TeV analysis on 100 GeV data
                               (audit D02), and it reads that ceiling from the
                               DSS keywords gtselect writes into the header.
No event-class or event-type cut is applied here; those are applied downstream
per component by the Principe configuration, exactly as with the FSSC cones.

Speed: gtselect is handed only the weekly files whose [TSTART, TSTOP] overlaps
the event's window (~33 weeks of the ~880-week mission), instead of the whole
mirror. gtselect's own time cut is unchanged, so the output is identical -- it
simply stops opening files that cannot contribute an event. Pass
--no-time-filter to restore the old whole-mirror behaviour.

Output: <outdir>/<EVENT>/<EVENT>_PH00.fits  (one file per event)

Usage (needs the Fermitools environment):
    conda activate fermi_env      # or fermipy
    python make_cones_from_weekly.py \
        --weekly /path/to/lat/weekly/photon \
        --catalog ../sample/fbot_catalog_tiered.csv \
        --outdir ../data/ft1_1tev [--tiers G1,G2] [--jobs 8]

Weekly files are usually named lat_photon_weekly_wNNN_p305_v001.fits (or
similar); pass --pattern to override the glob if your mirror differs.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from astropy.io import fits

QUERY_RADIUS = 30.0
DT = 10_000_000
EMIN, EMAX = 100, 1_000_000
MISSION_TSTART, MISSION_TSTOP = 239557417.0, 797361626.0


def sanitize(n):
    return re.sub(r'[^A-Za-z0-9_.+-]', '_', n)


def has_1tev_ceiling(path):
    """Same check run_task.py's D02 guard applies, so failures surface here."""
    try:
        h = fits.getheader(path, 'EVENTS')
    except Exception:
        return False
    for k in h:
        if str(k).startswith('DSTYP') and h[k] == 'ENERGY':
            try:
                return float(str(h['DSVAL' + k[-1]]).split(':')[1]) >= EMAX
            except Exception:
                return False
    return False


def weekly_time_index(files, cache_path, jobs):
    """Map each weekly file to its (TSTART, TSTOP), cached across runs.

    gtselect applies the tmin/tmax cut itself, but only after opening and
    scanning every file it is handed. A +-1e7 s window spans ~33 weeks, so
    passing the whole mirror made each event re-read the entire mission (~45 min
    per event, 14 times over). Handing it only the overlapping weeks gives
    byte-identical output for a fraction of the I/O.  (Partha, 2026-08-18.)

    Files whose headers cannot be read keep times of None and are always
    included: never drop data we cannot prove is out of range.
    """
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            cache = {}

    def stamp(p):
        st = p.stat()
        return f'{st.st_size}:{int(st.st_mtime)}'

    def read_one(p):
        key = str(p)
        mark = stamp(p)
        hit = cache.get(key)
        if hit and hit.get('stamp') == mark:
            return key, hit
        rec = {'stamp': mark, 'tstart': None, 'tstop': None}
        for ext in (0, 'EVENTS'):
            try:
                h = fits.getheader(p, ext)
                if 'TSTART' in h and 'TSTOP' in h:
                    rec['tstart'] = float(h['TSTART'])
                    rec['tstop'] = float(h['TSTOP'])
                    break
            except Exception:
                continue
        return key, rec

    with ThreadPoolExecutor(max_workers=max(jobs, 8)) as ex:
        index = dict(ex.map(read_one, files))
    try:
        cache_path.write_text(json.dumps(index))
    except Exception:
        pass
    return index


def weeks_overlapping(files, index, tmin, tmax):
    """Weekly files whose span intersects [tmin, tmax] (unknown spans kept)."""
    keep = []
    for p in files:
        rec = index.get(str(p)) or {}
        ts, te = rec.get('tstart'), rec.get('tstop')
        if ts is None or te is None or (ts <= tmax and te >= tmin):
            keep.append(p)
    return keep


def build_cone(row, weekly_list, outdir, env, weekly=None, index=None):
    name = row['name']
    d = outdir / sanitize(name)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f'{sanitize(name)}_PH00.fits'
    if out.exists() and has_1tev_ceiling(out):
        return name, 'cached'

    t0 = float(row['t0_met'])
    tmin = max(t0 - DT, MISSION_TSTART)
    tmax = min(t0 + DT, MISSION_TSTOP)
    if tmax <= tmin:
        return name, 'outside_mission_span'

    # hand gtselect only the weeks that can contain events in [tmin, tmax];
    # the cut it applies is unchanged, so the output is identical
    n_used = n_all = 0
    if weekly is not None and index is not None:
        subset = weeks_overlapping(weekly, index, tmin, tmax)
        n_used, n_all = len(subset), len(weekly)
        if subset:
            weekly_list = d / 'weekly_subset.txt'
            weekly_list.write_text('\n'.join(str(x) for x in subset) + '\n')

    # per-event PFILES sandbox: concurrent fermitools jobs otherwise race on the
    # shared parameter files (bug catalogue B-20)
    pf = d / 'pfiles'
    pf.mkdir(exist_ok=True)
    e = dict(env)
    e['PFILES'] = f"{pf.resolve()};{Path(sys.prefix) / 'share' / 'fermitools' / 'syspfiles'}"

    cmd = (f'gtselect infile=@{Path(weekly_list).resolve()} outfile={out.resolve()} '
           f"ra={float(row['ra_deg']):.6f} dec={float(row['dec_deg']):.6f} "
           f'rad={QUERY_RADIUS} tmin={tmin:.3f} tmax={tmax:.3f} '
           f'emin={EMIN} emax={EMAX} zmax=180 evclass=INDEF evtype=INDEF '
           f'clobber=yes')
    r = subprocess.run(cmd, shell=True, cwd=str(d), env=e,
                       capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        return name, f'gtselect_failed: {(r.stdout + r.stderr)[-160:]}'
    if not has_1tev_ceiling(out):
        return name, 'FAILED D02 CHECK: energy ceiling below 1 TeV'
    with fits.open(out) as h:
        n = len(h['EVENTS'].data)
    span = f', {n_used}/{n_all} weeks read' if n_all else ''
    return name, f'ok ({n} events{span})'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weekly', required=True, help='directory of LAT weekly photon files')
    ap.add_argument('--pattern', default='*PH*.fits',
                    help='glob for the weekly files (default: *PH*.fits)')
    ap.add_argument('--catalog', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--tiers', default='G1,G2')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--no-time-filter', action='store_true',
                    help='hand gtselect the whole mirror (the pre-2026-08-18 '
                         'behaviour); use if the time index looks wrong')
    a = ap.parse_args()

    weekly = sorted(Path(a.weekly).glob(a.pattern))
    if not weekly:
        raise SystemExit(f'no weekly files matching {a.pattern!r} under {a.weekly}')
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    listfile = outdir / 'weekly_files.txt'
    listfile.write_text('\n'.join(str(p) for p in weekly) + '\n')
    print(f'{len(weekly)} weekly files -> {listfile}')

    tiers = set(a.tiers.split(','))
    rows = [r for r in csv.DictReader(open(a.catalog))
            if r.get('tier') in tiers and (r.get('t0_met') or '').strip()]
    print(f'{len(rows)} events, tiers {sorted(tiers)}; '
          f'cone {QUERY_RADIUS} deg, +-{DT:.0e} s, {EMIN}-{EMAX} MeV')

    index = None
    if not a.no_time_filter:
        print('indexing weekly file times (cached after the first run)...',
              flush=True)
        index = weekly_time_index(weekly, outdir / 'weekly_time_index.json',
                                  a.jobs)
        known = sum(1 for v in index.values() if v.get('tstart') is not None)
        print(f'  {known}/{len(weekly)} files carry TSTART/TSTOP; '
              f'{len(weekly) - known} unreadable and will always be included')

    env = dict(os.environ)
    results = {}
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(build_cone, r, listfile, outdir, env,
                          weekly if index else None, index) for r in rows]
        for i, f in enumerate(futs, 1):
            name, status = f.result()
            results[name] = status
            print(f'[{i}/{len(rows)}] {name}: {status}', flush=True)

    (outdir / 'download_status.csv').write_text(
        '\n'.join(f'{k},{"done" if v.startswith(("ok", "cached")) else v}'
                  for k, v in sorted(results.items())) + '\n')
    bad = {k: v for k, v in results.items()
           if not v.startswith(('ok', 'cached'))}
    print('\nsummary:', len(results) - len(bad), 'ok,', len(bad), 'failed')
    if bad:
        for k, v in bad.items():
            print(f'  FAILED {k}: {v}')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
