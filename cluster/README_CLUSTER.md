# FBOT binned campaign — cluster package

Runs the audit-corrected Principe-configuration binned analysis at scale, on
**any** SLURM or PBS cluster (LSU HPC = SLURM; use the PBS wrapper on a
Torque/PBS system such as, possibly, Partha's). Nothing here is site-specific
except `cluster_config.yaml`.

## What is baked in (vs. the pre-audit local runs)

| audit ID | fix, active in this package |
|---|---|
| D01 | downstream extraction (`collect_stack.py`) treats surfaces as **TS**, uses the 2.71 drop; validated to 8 significant figures against the auditor's independent derivation |
| D02 | analysis runs on a **0.1–1000 GeV** data tree; `run_task.py` refuses to start if the FT1 energy ceiling is below config `emax` |
| D03 | energy dispersion active in the actual null/scan likelihoods (fork commit `24c84ee`) |
| D04 | Principe 2° catalog-source freedom applied in null AND scan (config `free_radius_deg`; set 0 for Karwin's freeze-all) |
| D16 | index-aware band conversion C100(Γ); no Γ=2 shortcut on other slices |
| D27 | full-precision likelihood output; per-run `task_meta.json`; stack manifest with input hashes |

## One-time setup on the cluster

```bash
# 1. stage the tree (rsync from the Mac or a shared filesystem)
rsync -a cluster/ Fermi_Stacking_Analysis/ sample/ refdata/ $CLUSTER:$CAMPAIGN_ROOT/
#    refdata/ needs: gll_iem_v07.fits, iso_P8R3_SOURCE_V3_v1.txt,
#    iso_P8R3_SOURCE_V3_PSF1_v1.txt, iso_P8R3_SOURCE_V3_PSF2_v1.txt, gll_psc_v35.fit
#    (all ship with fermitools / the FSSC; copy from the local env's share dir)

# 2. environment
conda env create -f environment.yml     # fermipy 1.3.1 + fermitools 2.2.0

# 3. verify the fork
cd $CAMPAIGN_ROOT/Fermi_Stacking_Analysis && git log --oneline -1   # expect 24c84ee

# 4. edit cluster_config.yaml: campaign_root + confirm scope
```

## Data (audit D02 — do this FIRST, wherever bandwidth is good)

```bash
python download_ft1_1tev.py --catalog ../sample/fbot_catalog_tiered.csv \
    --outdir ../data/ft1_1tev            # ~14 events for G1/G2; checkpointed
# then, if downloading at LSU but computing elsewhere:
rsync -a ../data/ft1_1tev $CLUSTER:$CAMPAIGN_ROOT/data/
```
The FT2 spacecraft file must also be staged to `data/ft2.fits`.

## Run

```bash
python make_manifest.py --config cluster_config.yaml     # -> tasks.txt
# SLURM (LSU):
sbatch --array=1-$(wc -l < tasks.txt)%20 submit_slurm.sh
# PBS:
qsub -t 1-$(wc -l < tasks.txt)%20 submit_pbs.sh
```
Tasks are independent and idempotent (a completed task is skipped), so a
partial campaign is resumed by regenerating tasks.txt and resubmitting.
Budget ≈ 3 h/task at the 1e5–1e7 s windows; 84 tasks for full G1/G2 scope
(14 events × 6 windows) ⇒ one overnight run at %20 concurrency.

## Collect

```bash
for W in post_100ks post_1e6 post_1e7 pre_100ks pre_1e6 pre_1e7; do
  python collect_stack.py --config cluster_config.yaml --window $W
done
# -> runs/STACK_<window>.npz + .json  (manifest: input hashes, corrected ULs)
rsync -a $CLUSTER:$CAMPAIGN_ROOT/runs/STACK_* back_to_the_mac/
```

## Validation contract

Before ANY number reaches the manuscript:
1. `STACK_post_100ks` from the cluster must agree with the local unbinned stack
   at Γ=2 within tens of percent (pre-audit corrected seam: ratio ≈ 0.76 on the
   old flawed surfaces; the new edisp+freedom+1TeV surfaces will differ — that
   difference is the physics of the configuration change and must be reported).
2. The `.json` manifests, not ad-hoc extraction, are the provenance source.
3. Every rerun updates `NUMBERS_PROVENANCE.md` and appends to `supervision.md`.
