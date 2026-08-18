# Fermi-LAT FBOT campaign — cluster repository

A binned-likelihood search for 0.1–1000 GeV emission from 14 luminous fast blue
optical transients (AT2018cow-like events). Each task analyses one event in one
post- or pre-discovery time window (10⁵, 10⁶, 10⁷ s) in the configuration of
Principe et al. (2023) — three jointly fitted, energy-dependent event-type
components — scanned over a 2D grid of flux × photon index. **84 tasks.**

The cluster runs the per-event scans. Cross-event stacking and all
interpretation happen back at the home institution. Results so far are nulls,
so the science is in the *depth* of the upper limits — which is why the
configuration details are not negotiable.

Questions: Salim (vikas.chand.physics@gmail.com).

---

## Quickstart

```bash
git clone https://github.com/vikas-chand/fbot-lat-cluster.git FBOTs_LAT
cd FBOTs_LAT

# 1. Verify you have the modified pipeline, not upstream (see Provenance below)
git log --oneline | grep 854d7b0
#   -> 854d7b0 Portability: resolve 4FGL catalog and extdir from environment
#   If this prints nothing, STOP and contact Salim.

# 2. Environment (~15 min, one time; use an interactive job if your cluster
#    forbids conda on login nodes)
conda env create -f cluster/environment.yml    # creates env "fermipy"
conda activate fermipy

# 3. Reference data — copied out of the env, not downloaded
mkdir -p refdata
cp $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/gll_iem_v07.fits \
   $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/iso_P8R3_SOURCE_V3_v1.txt \
   $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/iso_P8R3_SOURCE_V3_PSF1_v1.txt \
   $CONDA_PREFIX/share/fermitools/refdata/fermi/galdiffuse/iso_P8R3_SOURCE_V3_PSF2_v1.txt \
   refdata/

# 4. The one genuine download: 4FGL-DR4 (~80 MB). The run refuses to start
#    without it and names the file.
curl -L -o refdata/gll_psc_v35.fit \
  https://fermi.gsfc.nasa.gov/ssc/data/access/lat/14yr_catalog/gll_psc_v35.fit

# 5. Photon cones, cut from your own LAT weekly mirror (no bulk transfer)
cd cluster
python make_cones_from_weekly.py \
    --weekly /path/to/your/lat/weekly/photon \
    --catalog ../sample/fbot_catalog_tiered.csv \
    --outdir ../data/ft1_1tev --jobs 8

# 6. Point two lines of cluster/cluster_config.yaml at your paths, then:
python make_manifest.py --config cluster_config.yaml   # writes tasks.txt (~84)
sbatch  --array=1-$(wc -l < tasks.txt)%20 submit_slurm.sh   # SLURM
qsub -t 1-$(wc -l < tasks.txt)%20        submit_pbs.sh      # PBS/Torque
```

Per task: 1 node, 4 cores, ≤8 GB, ~8–10 h measured (16 h walltime for margin).
At `%20` concurrency the 84 tasks are about one day.

**Full step-by-step, including the known non-problems and what to do when
something actually breaks: [`cluster/INSTRUCTIONS_FOR_PARTHA.md`](cluster/INSTRUCTIONS_FOR_PARTHA.md).**
Read that before the first submit — this page is only the shape of the job.

## Resuming

`make_manifest.py` lists only what is left. Completed tasks are skipped
automatically; nothing is recomputed or corrupted by resubmission. After a node
death or walltime kill, re-run the manifest and resubmit.

## What to send back

```
runs/STACK_*.npz
runs/STACK_*.json
runs/*/task_meta.json
cluster/logs/          (only if something failed)
```

A few MB total. Please do **not** post-process the surfaces or extract upper
limits on your side — the crossing conventions and band conversions live in
`collect_stack.py` and were cross-validated against an independent audit; a
different extraction would not be comparable.

## Provenance — read this before swapping in your own install

`Fermi_Stacking_Analysis/` is Chris Karwin's public pipeline
([ckarwin/Fermi_Stacking_Analysis](https://github.com/ckarwin/Fermi_Stacking_Analysis),
Apache-2.0), **modified**. Installing upstream instead will not work and, worse,
may appear to work:

| Our commit | Change | If you use upstream instead |
|---|---|---|
| `854d7b0` | 4FGL catalog + extdir resolved from the environment | **All 84 tasks fail in preprocessing** — upstream bakes one machine's absolute paths into every fermipy config |
| `24c84ee` | Real energy dispersion, optional catalog freedom, full precision | Runs, but the numbers no longer match the adopted configuration |
| `2d6a684` | pandas 2.3.3 / Python 3.9+ | Breaks against the env in `environment.yml` |
| `bc6ec7d` | Portability + custom component schemes | Three-component Principe scheme unavailable |

The changes are 17 hunks inside `StackingAnalysis` and `MakeStack`, not settings
that calling code can pass in — which is why the pipeline is vendored here
rather than listed as a dependency.

- Full diff vs upstream: [`patches/fbot-local-vs-upstream.patch`](patches/fbot-local-vs-upstream.patch)
- Upstream base commit: `patches/UPSTREAM_BASE_COMMIT`
- Licensing and the statement of changes: [`NOTICE`](NOTICE)

The four commits are preserved with their original hashes in this repository's
history (imported with `git subtree`), which is what the `grep 854d7b0` check in
the quickstart verifies.
