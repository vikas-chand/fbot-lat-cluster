# READ ME FIRST — the whole job in one page

Hi Partha — everything is in this repo; there is nothing to unpack and nothing
to download from anywhere else except one catalog file.

This page is the five-minute version. The full step-by-step, with troubleshooting
and the list of harmless warnings you can ignore, is
[`cluster/INSTRUCTIONS_FOR_PARTHA.md`](cluster/INSTRUCTIONS_FOR_PARTHA.md).
Questions any time: Salim (vikas.chand.physics@gmail.com).

**What it is.** A Fermi-LAT search for 0.1–1000 GeV emission from 14 luminous
fast blue optical transients (AT2018cow-like). 84 independent tasks = 14 events
× 6 time windows. Each task is a binned likelihood scan over a 2D grid of flux ×
photon index, in the configuration of Principe et al. (2023).

## Setup — about 30 minutes, once

```bash
# 1. get it
git clone https://github.com/vikas-chand/fbot-lat-cluster.git FBOTs_LAT
cd FBOTs_LAT

# 2. confirm you have OUR pipeline, not upstream Karwin (see the warning below)
git log --oneline | grep 854d7b0        # must print a line; if not, stop and tell Salim

# 3. environment (interactive job if your cluster blocks conda on login nodes)
conda env create -f cluster/environment.yml     # fermitools 2.2.0 + fermipy 1.3.1
conda activate fermipy

# 4. reference data: 4 diffuse/isotropic files copied out of the env, plus the
#    4FGL catalog by curl -- exact commands in README.md, steps 3 and 4
```

```bash
# 5. cut the 30-degree photon cones from your own LAT weekly mirror
#    (this is why nothing large has to be shipped to you). Resumable, and it
#    verifies its own output.
cd cluster
python make_cones_from_weekly.py \
    --weekly /path/to/your/lat/weekly/photon \
    --catalog ../sample/fbot_catalog_tiered.csv \
    --outdir ../data/ft1_1tev --jobs 8

# 6. edit two lines of cluster/cluster_config.yaml: campaign_root, conda_env.
#    Please leave the `analysis:` block alone -- those values are the adopted
#    configuration and have to match the paper.
```

## Run — from the `cluster/` directory

```bash
python make_manifest.py --config cluster_config.yaml
wc -l tasks.txt                                    # expect ~84

sbatch  --array=1-$(wc -l < tasks.txt)%20 submit_slurm.sh   # SLURM
qsub -t 1-$(wc -l < tasks.txt)%20        submit_pbs.sh      # PBS/Torque
```

Per task: 1 node, 4 cores, 8 GB, 16 h walltime (they measure 8–10 h). At `%20`
concurrency the 84 tasks are about one day. **To resume after anything** — node
death, walltime kill, partial submit — just re-run `make_manifest.py` and
resubmit. Finished tasks are skipped, and a killed task keeps its own partial
work: preprocessing is reused, and finished index rows are reused one by one, so
a job killed at index 2.9 of 4.0 restarts near 2.9 instead of from zero. A row is
only reused if it is complete, correctly labelled and finite. `FS_RESUME=0`
forces a clean recompute.

## Then run the stacking — this part is yours too

Easy to miss, so stated plainly: the cross-event stack runs on your side, not
ours. When the queue drains:

```bash
for W in post_100ks post_1e6 post_1e7 pre_100ks pre_1e6 pre_1e7; do
  python collect_stack.py --config cluster_config.yaml --window $W
done
```

## What to send back — a few MB total

```
runs/STACK_*.npz
runs/STACK_*.json
runs/*/task_meta.json
cluster/logs/            (only if something failed)
```

Please don't extract upper limits or post-process the surfaces yourself. The
crossing conventions and band conversions already live in `collect_stack.py` and
were cross-validated against an independent audit; a different extraction would
not be comparable to ours.

## Two things that will cost you a day if missed

- **Do not install Karwin's upstream `fermi_stacking` from GitHub or pip.** Ours
  carries four small commits his does not. Without them every task fails in
  preprocessing — upstream bakes one machine's absolute paths into every fermipy
  config — and any task that did run would not match our adopted configuration.
  Use only what is in this repo. Details and the full diff: [`NOTICE`](NOTICE)
  and [`patches/`](patches).

- **The FT2 spacecraft file.** You need the standard full-mission
  `lat_spacecraft_merged.fits`. If your mirror has it, point `paths.ft2` at it.
  If not, tell Salim and he will send it (2.6 GB) — it is the one thing that
  might still need transferring.

Thanks for running this — it turns a two-week laptop job into one night.
