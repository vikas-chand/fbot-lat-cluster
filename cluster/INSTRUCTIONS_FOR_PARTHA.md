# Fermi-LAT FBOT campaign — cluster instructions

Hi Partha,

Thanks for running this. Below is everything from cloning to sending results
back. It is written so no step needs guessing; if anything still does, message
Salim (vikas.chand.physics@gmail.com).

## 1. What this is (one paragraph)

We are searching Fermi-LAT data for 0.1–1000 GeV emission from 14 luminous
fast blue optical transients (AT2018cow-like events). Each task is a binned
likelihood analysis of one event in one post- or pre-discovery time window
(10⁵, 10⁶, or 10⁷ s), in the configuration of Principe et al. 2023 (three
jointly fitted energy-dependent event-type components), scanned over a
2D grid of flux × photon index, using Chris Karwin's public `fermi_stacking`
pipeline with four small, documented local commits.

**Your cluster runs all three computing stages**: preprocessing, the 84
per-event likelihood scans (the expensive part), and then the cross-event stack
itself — `collect_stack.py`, six windows, section 6. What happens back here is
validation and interpretation: the 10⁵ s seam check against our unbinned stack,
and the manuscript numbers. So please do run section 6; the stacked surfaces,
not the per-event arrays, are what we need back.

Everything is a null result so far — the science is in the depth of the upper
limits, which is why the configuration details below matter.

## 2. Getting it

Everything is in one private repository — no tarball, nothing to unpack:

```bash
git clone https://github.com/vikas-chand/fbot-lat-cluster.git FBOTs_LAT
cd FBOTs_LAT
```

```
cluster/                     the campaign scripts (this file lives here too)
Fermi_Stacking_Analysis/     Karwin's pipeline, MODIFIED (see NOTICE + patches/)
sample/fbot_catalog_tiered.csv
README.md                    quickstart; this file is the full version
```

First thing after cloning — verify you have the modified pipeline and not
upstream:

```bash
git log --oneline | grep 854d7b0
# must print: 854d7b0  Portability: resolve 4FGL catalog and extdir ...
```

If it prints nothing, stop and tell Salim. Upstream Karwin will not run this
campaign: it hardcodes another machine's absolute paths into every fermipy
config, and it lacks the configuration fixes the adopted numbers depend on.
The full diff against upstream is in `patches/fbot-local-vs-upstream.patch`.

## 3. Prerequisites

1. **Conda environment** (one-time, ~15 min):
   ```bash
   conda env create -f cluster/environment.yml     # creates env "fermipy"
   ```
   This installs fermitools 2.2.0 + fermipy 1.3.1 from conda-forge/fermi.
   If your cluster forbids conda on login nodes, build it in an interactive job.

2. **Reference data** (copy, not download):
   ```bash
   mkdir -p $CAMPAIGN_ROOT/refdata
   conda activate fermipy
   cp $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/gll_iem_v07.fits \
      $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/iso_P8R3_SOURCE_V3_v1.txt \
      $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/iso_P8R3_SOURCE_V3_PSF1_v1.txt \
      $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/iso_P8R3_SOURCE_V3_PSF2_v1.txt \
      $CAMPAIGN_ROOT/refdata/
   ```
   Plus the 4FGL-DR4 catalog `gll_psc_v35.fit` (~80 MB), straight from the FSSC:

   ```bash
   curl -L -o $CAMPAIGN_ROOT/refdata/gll_psc_v35.fit \
     https://fermi.gsfc.nasa.gov/ssc/data/access/lat/14yr_catalog/gll_psc_v35.fit
   ```
   The run refuses to start if this file is missing, and says so by name.

3. **Photon + spacecraft data — you already have what is needed.**
   You hold the LAT weekly photon files, so nothing large has to be shipped.
   The pipeline wants one 30-degree cone per event (not the all-sky weeklies),
   so cut them locally with the script included for exactly this:

   ```bash
   conda activate fermipy
   cd cluster
   python make_cones_from_weekly.py \
       --weekly /path/to/your/lat/weekly/photon \
       --catalog ../sample/fbot_catalog_tiered.csv \
       --outdir ../data/ft1_1tev --jobs 8
   ```
   It replicates the campaign's selection exactly (30 deg, t0 +- 1e7 s,
   100 MeV - 1000 GeV), writes `data/ft1_1tev/<EVENT>/`, is resumable, and
   verifies each output itself. ~14 gtselect passes over the weeklies.

   ⚠ The 1 TeV upper bound is not cosmetic: `run_task.py` refuses to start if
   the FT1 energy ceiling is below the configured `emax` (that guard exists
   because an earlier run silently analysed 100 GeV data in a 1 TeV
   configuration, creating eight fictitious empty bins). The script applies the
   same check and fails loudly rather than handing you bad cones.

   You also need the **FT2 spacecraft file** (`data/ft2.fits`) — the standard
   full-mission `lat_spacecraft_merged.fits`. If your mirror has it, point
   `paths.ft2` at it; if not, tell Salim and he will send it (2.6 GB).

   *(Alternative, if you would rather fetch fresh cones from the FSSC and have
   outbound HTTPS: `python download_ft1_1tev.py --catalog
   ../sample/fbot_catalog_tiered.csv --outdir ../data/ft1_1tev`. Checkpointed.)*

## 4. Configure (one file, two lines)

Edit `cluster/cluster_config.yaml`:

```yaml
campaign_root: /your/absolute/path/FBOTs_LAT     # <- change this
conda_env: fermipy                               # <- if you named it differently
```

Leave the `analysis:` block alone — those values (energy range, 10° ROI,
2° catalog freedom, energy dispersion on) are the adopted configuration and
must match the paper. If a run problem tempts you to change one, tell Salim
instead.

## 5. Run

```bash
cd cluster
conda activate fermipy
python make_manifest.py --config cluster_config.yaml   # writes tasks.txt
wc -l tasks.txt                                        # expect ~84
```

**PBS/Torque:**
```bash
qsub -t 1-$(wc -l < tasks.txt)%20 submit_pbs.sh
```
**SLURM:**
```bash
sbatch --array=1-$(wc -l < tasks.txt)%20 submit_slurm.sh
```

The `%20` caps concurrency at 20 — raise or lower it to fit your allocation;
correctness does not depend on it. Each task: 1 node, 4 cores, ≤8 GB,
~8-10 h measured on a 16-core laptop at ~3.6 s per Minuit grid point (the scan is 2,480 points x 3 joint components and its cost is set by the grid, not the photon count — all windows cost about the same). Give 16 h walltime for margin; at %20 concurrency the 84 tasks are one day on the cluster.

**Resuming after anything** (node death, walltime kill, partial submit):
```bash
python make_manifest.py --config cluster_config.yaml   # lists only what's left
qsub -t 1-$(wc -l < tasks.txt)%20 submit_pbs.sh
```
Completed tasks are skipped automatically. Since 2026-08-20 a killed task also
keeps its own partial work: finished preprocessing is reused, and finished index
rows are reused row by row, so a job killed at index 2.9 of 4.0 restarts near 2.9
rather than from the beginning. Expect a line like

```
[resume] AT2018cow PSF 2: reused 20/31 completed index rows
```

A row is only reused if it is complete, correctly labelled and finite; anything
short, truncated mid-line or containing NaN is recomputed. If the scan
configuration changes (flux grid, energy ceiling, edisp, or a re-run
preprocessing that changes the ROI model), preserved rows are discarded rather
than mixed. `FS_RESUME=0` forces a clean recompute.

## 6. Verify and collect

When the queue drains:

```bash
# quick health check — count finished tasks:
ls $CAMPAIGN_ROOT/runs/*/Add_Stacking/Numpy_Arrays/*.npy | wc -l
# any task that failed leaves no .npy; its log is in cluster/logs/

# build the stacked surfaces + provenance manifests:
for W in post_100ks post_1e6 post_1e7 pre_100ks pre_1e6 pre_1e7; do
  python collect_stack.py --config cluster_config.yaml --window $W
done
```

## 7. What to send back

Only these (small — a few MB total):

```
$CAMPAIGN_ROOT/runs/STACK_*.npz
$CAMPAIGN_ROOT/runs/STACK_*.json
$CAMPAIGN_ROOT/runs/*/task_meta.json
cluster/logs/            (only if something failed)
```

Please do NOT post-process the surfaces or apply upper-limit extractions on
your side — the crossing conventions and band conversions are already encoded
in `collect_stack.py` and were cross-validated against an independent audit;
a different extraction would not be comparable.

## 8. Known non-problems

- `SKIP already complete` — normal on resubmission.
- `no FT1 cone — recorded, skipping` (exit 3) — that event has no data for
  that window; it is accounted for, not an error.
- `Zero exposure!` from fermipy — the LAT was not pointing there in that
  window; the task records it and moves on.
- A `SyntaxWarning` about `\m` from an old plotting line in Stack.py — cosmetic.

## 9. If something actually breaks

Send Salim the task's log file (`cluster/logs/fbot-binned_*_<N>.out`, where N
is the tasks.txt line number) and the corresponding `runs/<EVENT>_<WINDOW>/`
directory listing. The three failure modes we would genuinely want to know
about: the D02 guard firing (wrong data staged), a missing refdata file
(isotropic PSF templates are the usual suspect), and conda activation issues
inside batch jobs (edit the `source .../conda.sh` line in the wrapper to your
cluster's convention).

Thanks again — this turns a two-week laptop job into one night.
