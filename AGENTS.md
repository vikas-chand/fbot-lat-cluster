# Agent guide — running the FBOT LAT campaign on a cluster

You are operating someone else's science campaign on their cluster. The analysis
configuration is already decided, audited, and frozen; your job is to *execute*
it faithfully and to *report* honestly, not to improve it. A run that finishes
with quietly-adjusted settings is worse than a run that fails loudly, because
the numbers reach a manuscript.

Human owner: Salim (vikas.chand.physics@gmail.com). Escalate rather than guess.

## What the campaign is

A Fermi-LAT binned-likelihood search for 0.1–1000 GeV emission from 14 luminous
fast blue optical transients. **84 tasks = 14 events × 6 time windows**
(post/pre discovery at 10⁵, 10⁶, 10⁷ s). Each task scans a 2D grid of flux ×
photon index over three jointly fitted, energy-dependent event-type components,
in the configuration of Principe et al. (2023). Results so far are nulls; the
science is the *depth* of the upper limits, so configuration fidelity is the
whole game.

## Hard rules — violating any of these invalidates the run

1. **Never edit the `analysis:` block of `cluster/cluster_config.yaml`**
   (`emin_mev`, `emax_mev`, `roi_radius_deg`, `free_radius_deg`, `edisp`). These
   are audited values that must match the paper. Only `campaign_root`,
   `conda_env`, and the `paths:` entries are site-specific and yours to set.
2. **Never install or substitute upstream `fermi_stacking`** (GitHub or pip). The
   vendored copy carries four commits upstream lacks; without them every task
   fails in preprocessing, and any that ran would not match the adopted
   configuration. See `NOTICE` and `patches/`.
3. **Never extract upper limits or post-process the stacked surfaces.** The
   crossing conventions and band conversions live in `collect_stack.py` and were
   cross-validated. Return the surfaces; interpretation happens at the home
   institution.
4. **Never delete or overwrite `runs/`.** It is the only copy of completed work.
   Resubmission is always safe; deletion is not.
5. **If a task fails, do not tune anything to make it pass.** Report it. A
   configuration change that turns a failure into a success is precisely the bug
   this campaign is guarding against.
6. **Do not commit or push to this repository.** It is upstream of the owner's
   analysis. Your outputs are data files, not code changes.

## Run order

Each phase ends in a VERIFY you should actually execute before moving on.

### Phase 0 — preflight

```bash
git log --oneline | grep 854d7b0
conda env create -f cluster/environment.yml && conda activate fermipy
```
Reference data into `refdata/`: `gll_iem_v07.fits`, `iso_P8R3_SOURCE_V3_v1.txt`,
`iso_P8R3_SOURCE_V3_PSF1_v1.txt`, `iso_P8R3_SOURCE_V3_PSF2_v1.txt` (copied from
`$CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/`), plus
`gll_psc_v35.fit` (4FGL-DR4) curl'd from the FSSC. Then set `campaign_root` and
`conda_env` in `cluster/cluster_config.yaml`.

VERIFY: `python -c "import fermipy, yaml; print('env ok')"` and
`ls refdata/` shows all five files. The `grep 854d7b0` above must print a line —
if it does not, STOP and tell the owner; you have the wrong pipeline.

### Phase 1 — photon cones

```bash
cd cluster
python make_cones_from_weekly.py --weekly <LAT weekly photon dir> \
    --catalog ../sample/fbot_catalog_tiered.csv \
    --outdir ../data/ft1_1tev --jobs 8
```
Resumable; it applies the campaign's own D02 energy-ceiling check, so a bad cone
fails at creation rather than mid-campaign.

VERIFY: `ls ../data/ft1_1tev/ | wc -l` ≈ 14 event directories, and the script
exits 0. Also confirm `paths.ft2` points at a real full-mission
`lat_spacecraft_merged.fits`; if the site has none, ask the owner to send it.

### Phase 2 — submit

```bash
python make_manifest.py --config cluster_config.yaml     # writes tasks.txt
wc -l tasks.txt                                          # expect ~84
sbatch  --array=1-$(wc -l < tasks.txt)%20 submit_slurm.sh
qsub -t 1-$(wc -l < tasks.txt)%20        submit_pbs.sh
```
Run these **from `cluster/`** — the wrappers read `tasks.txt` relative to the
working directory. Per task: 4 cores, 8 GB, 16 h walltime; measured cost is
8–10 h. `%20` is a throttle, not a correctness parameter.

VERIFY: the array is queued and the first task's log appears under
`cluster/logs/`.

### Phase 3 — wait, and resume

A task taking ten to twenty-four hours is normal, not a hang. To resume after
node death, walltime kill, or a partial submit, re-run `make_manifest.py` (it
lists only what is left) and resubmit. Completed tasks are skipped, and a killed
task now resumes from its last finished index row rather than restarting.

Do NOT "help" the resume: never delete `Stacked_Sources/` or
`Preprocessed_Sources/` to get a clean start, and never hand-edit a
`*_stacking_*.txt`. Those directories are the checkpoint. If a task refuses to
combine because rows are `nonfinite`, that means fits diverged — report it,
do not delete the rows and rerun until it passes.

VERIFY: `ls $CAMPAIGN_ROOT/runs/*/Add_Stacking/Numpy_Arrays/*.npy | wc -l`
climbs toward 84. A task that failed leaves no `.npy`; its log is in
`cluster/logs/`.

### Phase 4 — stack (this runs here, not at the home institution)

```bash
for W in post_100ks post_1e6 post_1e7 pre_100ks pre_1e6 pre_1e7; do
  python collect_stack.py --config cluster_config.yaml --window $W
done
```

VERIFY: six `STACK_*.npz` and six `STACK_*.json` exist, and each `.json` reports
a `pipeline_sha256`. That hash is checked at the far end against the owner's own
copy of the pipeline — it is how the run proves what produced it, so do not
hand-edit these files.

### Phase 5 — return

Send back only:
```
runs/STACK_*.npz
runs/STACK_*.json
runs/*/task_meta.json
cluster/logs/            (only if something failed)
```
A few MB total. Nothing else is needed, and nothing else should be modified.

## Expected messages that are NOT problems

- `SKIP already complete` — normal on resubmission.
- `no FT1 cone — recorded, skipping` (exit 3) — that event has no data in that
  window. Accounted for, not an error.
- `Zero exposure!` from fermipy — the LAT was not pointing there in that window.
  Recorded; the task moves on.
- A `SyntaxWarning` about `\m` from an old plotting line in `Stack.py` — cosmetic.

## Failures worth escalating immediately

- **The D02 guard fires** (`run_task.py` refuses to start because the FT1 energy
  ceiling is below the configured `emax`) — wrong data staged. Do not lower
  `emax` to satisfy it; that is the exact mistake the guard exists to prevent.
- **A missing `refdata` file** — usually one of the isotropic PSF templates.
- **Conda activation failing inside batch jobs** — adapt the
  `source .../conda.sh` line in the wrapper to the site's convention. This is the
  one edit to a submit script that is expected and fine.

When escalating, send the task's log (`cluster/logs/fbot-binned_*_<N>.out`, N =
the line number in `tasks.txt`) and a listing of the matching
`runs/<EVENT>_<WINDOW>/`. Say what you observed and what you did not change.

## Reporting to the human

Report progress in tasks completed out of 84 and windows stacked out of six.
State failures with their log paths rather than summarizing them as "some tasks
failed". If you were tempted to change a setting and did not, say so — that is
useful information, not noise.
