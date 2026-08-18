#!/usr/bin/env python3
"""
Download 0.1-1000 GeV FT1 cones for the binned campaign (audit D02).

The existing trees (data/ft1, data/ft1_transient) are capped at 100 GeV, so a
nominal 1 TeV binned analysis run on them carries eight fictitious empty bins
with nonzero model/exposure — this script exists so that never happens again.
run_task.py refuses to run if the FT1 DSS ceiling is below the config emax.

One cone per event: [t0 - 1e7 s, t0 + 1e7 s] (serves the 1e5/1e6/1e7 windows,
pre and post), 30 deg radius, 100 MeV - 1000 GeV. Checkpointed and resumable —
run it wherever bandwidth is good (LSU), then rsync data/ft1_1tev/ to the
compute cluster if that is elsewhere.

Usage: python download_ft1_1tev.py --catalog ../sample/fbot_catalog_tiered.csv \
           --outdir ../data/ft1_1tev [--tiers G1,G2] [--list]
"""
import argparse, csv, re, time
from pathlib import Path
import requests
from astropy.io import fits

QUERY_RADIUS = 30.0
DT = 10_000_000
EMIN, EMAX = 100, 1_000_000          # MeV — the point of this script
FT2_TSTART, FT2_TSTOP = 239557417.0, 797361626.0
FSSC = 'https://fermi.gsfc.nasa.gov/cgi-bin/ssc/LAT/LATDataQuery.cgi'


def sanitize(n):
    return re.sub(r'[^A-Za-z0-9_.+-]', '_', n)


def done(d):
    for f in sorted(d.glob('*_PH*.fits')):
        try:
            h = fits.getheader(f, 1)
            for k in h:
                if str(k).startswith('DSTYP') and h[k] == 'ENERGY':
                    if float(str(h[f'DSVAL{k[-1]}']).split(':')[1]) >= EMAX:
                        return True
        except Exception:
            pass
    return False


def fetch(name, ra, dec, met, outdir):
    d = outdir / sanitize(name); d.mkdir(parents=True, exist_ok=True)
    if done(d):
        print(f'  {name}: 1 TeV cone present'); return 'done'
    tmin, tmax = max(met - DT, FT2_TSTART), min(met + DT, FT2_TSTOP)
    q = requests.post(FSSC, data={
        'destination': 'query', 'coordfield': f'{ra:.5f}, {dec:.5f}',
        'coordsystem': 'J2000', 'shapefield': str(QUERY_RADIUS),
        'timefield': f'{tmin:.3f}, {tmax:.3f}', 'timetype': 'MET',
        'energyfield': f'{EMIN}, {EMAX}', 'photonOrExtendedOrNone': 'Photon',
        'spacecraft': 'off'}, timeout=120)
    m = re.search(r'may be found at <a href="(.*?)">', q.text)
    if not m:
        return 'no_link'
    est = re.search(r'complete is ([0-9]+) seconds', q.text)
    poll = max((int(est.group(1)) if est else 300) / 4, 20)
    for _ in range(60):
        time.sleep(poll)
        try:
            r = requests.get(m.group(1), timeout=60)
            if 'Query complete' in r.text:
                break
        except Exception:
            pass
    else:
        return 'poll_timeout'
    links = [l for l in re.findall(r'wget (https.*?fits)', r.text) if '_PH' in l]
    if not links:
        return 'no_data' if re.search(r'No data found', r.text, re.I) else 'no_files'
    for link in links:
        dest = d / link.split('/')[-1]
        with requests.get(link, stream=True, timeout=600) as resp:
            with open(dest, 'wb') as f:
                for c in resp.iter_content(65536):
                    f.write(c)
        print(f'    {dest.name} {dest.stat().st_size/1e6:.0f} MB')
    return 'done'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--catalog', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--tiers', default='G1,G2')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    tiers = set(a.tiers.split(','))
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(open(a.catalog))
            if r.get('tier') in tiers and r.get('t0_met')]
    print(f'{len(rows)} events, tiers {sorted(tiers)}, 0.1-1000 GeV, +-1e7 s, 30 deg')
    if a.list:
        for r in rows:
            print(f"  {r['tier']} {r['name']}")
        return
    status = {}
    for i, r in enumerate(rows):
        print(f'[{i+1}/{len(rows)}] {r["name"]}')
        status[r['name']] = fetch(r['name'], float(r['ra_deg']),
                                  float(r['dec_deg']), float(r['t0_met']), out)
        (out / 'download_status.csv').write_text(
            '\n'.join(f'{k},{v}' for k, v in sorted(status.items())) + '\n')
    print('summary:', {s: list(status.values()).count(s) for s in set(status.values())})


if __name__ == '__main__':
    main()
