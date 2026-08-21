# External audit of the FBOT cluster code

Date: 2026-08-20  
Auditor: Codex, independent read-only review  
Artefact audited: the tree at `/Users/salim/Desktop/Projects/FBOTs_LAT_cluster`, asserted by the brief to be public-mirror HEAD `0c46460`

## VERDICT — DO NOT RUN AS SHIPPED

The package is not safe for either cluster to run unattended. I found multiple independent paths to a plausible, completed, but scientifically wrong surface:

1. components 1 and 2 are evaluated with component 0's 85-degree livetime cube;
2. the D04 “free nearby sources” implementation is a silent no-op on standard Fermi XML, so catalog sources intended to be free within 2 degrees remain frozen;
3. the fixed mission stop truncates `AT2026dbl post_1e7` to 46.11441% of its requested post-discovery span while recording the full requested interval;
4. collection accepts partial, stale, extra, or wrong-identity event sets, and the return-side ingest can still print `ALL CHECKS PASSED`;
5. optimizer quality/status is recorded by the fork but discarded before stacking, so a failed likelihood cell can set an apparently deep upper limit;
6. a missing trailing component can become a valid-looking two-component surface;
7. the collector re-references surfaces that are already TS-relative to the null at a finite, non-null flux point.

The first three alone are stop-ship defects in the adopted analysis. The return-side validation gaps remove the intended last line of defence. Running two sites does not mitigate these defects: it makes shared deterministic defects agree, while site-dependent input/path defects can masquerade as physics.

This was a source audit plus standalone arithmetic. I did not run the Fermitools/fermipy pipeline because the specified environment is absent on this Mac. I did not open or create FITS files, generate renders, run Git, or modify any code/configuration/data. A source import transiently generated three Python bytecode cache files; the exact generated files and their empty directories were removed before handoff. The only retained written file is this report.

## A. CONFIGURATION

### A1. Zenith cut — WRONG

The suspected global clipping is **not** what happens. Fermipy copies the root configuration into each component and merges the component dictionary over it; its component setup then invokes `gtselect` separately. Therefore the values reaching `gtselect` are 85, 95, and 105 degrees. Root `zmax: 100` does not pre-filter the input and does not clip component 2. `gtmktime` follows each selected event file and has no later global-100 override. This agrees with the [Fermipy 1.3 component setup source](https://fermipy.readthedocs.io/en/1.3.0/_modules/fermipy/gtanalysis.html).

The analysis nevertheless becomes wrong later:

- `Fermi_Stacking_Analysis/fermi_stacking/preprocessing/Preprocess.py:637-644` starts the null-likelihood loop with `self.ltcube == "None"`, assigns `ltcube_00.fits` on component 0, then finds that same path valid and reuses it for components 1 and 2.
- `cluster/run_task.py:196-199` explicitly overwrites `inst.ltcube` with `ltcube_00.fits` after preprocessing.
- `Fermi_Stacking_Analysis/fermi_stacking/stacking/Stack.py:214-218` supplies that singleton path to every scan component's `BinnedObs`.

Thus component-1 and component-2 counts/source maps/binned exposure maps reflect 95/105-degree selections, but their manual null and scan observations use the 85-degree livetime cube. The FSSC explicitly requires the livetime correction to carry the same `zmax` used for the event cut; `gtltcube zmax=ZMAX` is part of the prescribed chain. See [FSSC, Precomputation of Livetime and Exposure](https://fermi.gsfc.nasa.gov/ssc/data/analysis/documentation/Cicerone/Cicerone_Likelihood/Exposure.html). The exposure/mean-PSF/DRM error does not cancel merely because the same wrong cube is used in the null and scan.

Exact fix: do not mutate or share `self.ltcube` across components. In both the null loop and `run_stacking`, construct a local `ltcube_0{j}.fits`, require it to exist, and verify its selection metadata against that component's source map/event products. Remove the assignment to `ltcube_00.fits` in `run_task.py`. Add a pre-scan invariant requiring exact component-indexed tuples for all three bands.

### A2. Event type and event class — WRONG/FRAGILE

The root/component interaction itself works as intended:

- component `evtype` overrides root `evtype: 3`, so no global-3 selection occurs first;
- root `evclass: 128` is inherited by every component;
- the requested event masks reaching component setup are 48, 56, and 63.

Masks 48 and 56 are the intended PSF2+PSF3 and PSF1+PSF2+PSF3 selections. Mask 63 is noncanonical: it combines FRONT/BACK bits 1+2 with PSF bits 4+8+16+32. FSSC says event-type partitions must not be mixed, and documents the all-event partition masks as 3, 60, and 960. See [FSSC Pass 8 event selections](https://fermi.gsfc.nasa.gov/ssc/data/access/lat/lat_data_products.html) and the official [`gtselect` help](https://raw.githubusercontent.com/fermi-lat/fermitools-fhelp/master/fhelp_files/gtselect.txt).

There is an important pinned-version qualification. Inspection of Fermitools 2.2 source shows that this particular 63 does not necessarily fail: its bit predicate selects the same Pass-8 photon rows as 60, the highest set bit chooses the PSF partition, and the response loader intersects the requested bits with the available PSF IRFs. Under that implementation, 63 behaves numerically like canonical PSF0123 = 60. This accidental equivalence is not a documented interface and is a portability hazard across builds/versions.

Principe et al. specify PSF2+3 below 300 MeV, PSF1+2+3 from 300 MeV to 1 GeV, and “all events” above 1 GeV; that wording does not choose FRONT/BACK partition 3 over all-PSF partition 60. See [Principe et al. 2023](https://arxiv.org/abs/2305.09428). The generic isotropic model is supported for all FRONT+BACK or all-PSF selections and therefore does not resolve the ambiguity; see [FSSC Background Models](https://fermi.gsfc.nasa.gov/ssc/data/access/lat/BackgroundModels.html).

Exact fix: change the high-energy component from 63 to canonical PSF0123 mask 60, which preserves the observed Fermitools-2.2 response decomposition. Do **not** silently change it to 3; that chooses a different partition/IRF decomposition. Add a regression check for selected event identities and loaded response identifiers.

### A3. Energy range and seams — CORRECT

`cluster/run_task.py:106-107` formats configured `1000000.0` with `:.0f`, so `%EMAX%` is replaced by the literal `1000000`. The three bands reaching the tools are:

- 100–300 MeV;
- 300–1000 MeV;
- 1000–1,000,000 MeV.

Fermitools 2.2 `RangeCut::accept` implements a nondegenerate energy range as `(minimum, maximum]`. Exactly 300 MeV therefore belongs only to component 0, and exactly 1000 MeV only to component 1. There is neither a seam gap nor double counting. Exactly 100 MeV is excluded by the common lower-threshold convention; this is not an inter-component seam.

The fork's `PowerLaw2` target normalization in `Stack.py:109-124` is over the common full 100–1,000,000 MeV band, so the component likelihoods share the intended integral-flux parameter rather than three unrelated band fluxes.

### A4. Component count — WRONG

`cluster/run_task.py:201` sets `ncomp = len(glob("srcmap_0*.fits"))`. It does not require three files, exact IDs `{00,01,02}`, or the matching ltcube/bexpmap/XML/null products. It then scans `range(ncomp)` and calls `combine_likelihood`.

`Fermi_Stacking_Analysis/fermi_stacking/stacking/Stack.py:443-526` discovers the likelihood directories that happen to exist and sums them. If preprocessing returns with only trailing component 2 missing, the driver scans components 0 and 1, `combine_likelihood` accepts them, and it writes a plausible 31×80 two-component `.npy`. That is not a valid adaptive analysis; it silently removes the highest-energy band. A missing middle component may fail differently or cause component 2 to be ignored, so the behavior also depends on which artefact is absent.

A physically empty/zero-count band should still have a defined component response and a zero contribution. Missing products are not an acceptable representation of zero data.

Exact fix: assert the exact indexed set `{00,01,02}` for source maps, binned exposure maps, livetimes, component XMLs, and null likelihoods before any scan. Pass expected IDs explicitly to `combine_likelihood`; reject every other set. Represent a genuine zero-exposure component with an explicit, identity-bearing terminal status and a mathematically verified zero contribution.

## B. STACK MATHS

### B5. `stack += arr - arr[:, :1]` — WRONG

The saved array is already a null-referenced TS surface. In `Fermi_Stacking_Analysis/fermi_stacking/stacking/Stack.py:487-494`, each cell is computed as

```text
TS(Γ,F) = 2 [log L(Γ,F) − log L(null)]
```

and that quantity is saved at `Stack.py:496-526`. The first flux column is not the null: `Stack.py:238-256` scans 80 positive values from `10^-11` through `10^-3 ph cm^-2 s^-1`. Therefore `cluster/collect_stack.py:95` changes the intended sum from

```text
Σe TSe(Γ,F)
```

to

```text
Σe TSe(Γ,F) − Σe TSe(Γ,10^-11).
```

The exact campaign error is the negative of the summed first-column TS, row by row. Those surfaces do not exist in this checkout, so its actual magnitude cannot be reported honestly. As a scale demonstration, a residual first-column TS of +0.1 for each of 14 events shifts that index row by −1.4 TS.

For a fixed-index upper limit, a constant row offset cancels when the curve is again referenced to its own maximum, so the fixed-row crossing is invariant. It does **not** generally cancel after profiling over index: the row-dependent offsets can change which Γ supplies `max(axis=0)`, the profile shape, and the 2-D surface interpretation.

Exact fix: sum `arr` itself, after checking that every surface uses the stated common null. Better, represent `F=0` explicitly outside the logarithmic scan (or store the null likelihood separately), prepend its exact TS=0 value during extraction, and test null anchoring. Do not use a finite scan column as “null.”

### B6. Drop 2.71 — CORRECT asymptotically; calibration and implementation guards are incomplete

For one scalar flux parameter of interest, the one-sided 95% Gaussian threshold is

```text
1.644853626951^2 = 2.7055434541 ≈ 2.71
```

on a `2 Δlog L` surface. Equivalently, the likelihood drop is `2.71/2`. This is the convention used by the [FSSC upper-limit example](https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/upper_limits.html).

Maximizing over photon index does not turn the interval into a two-parameter joint contour: flux remains the single parameter of interest and Γ is a profiled nuisance parameter. Therefore the asymptotic profile-likelihood crossing remains 2.71, not the two-degree-of-freedom contour threshold. The fixed-index and profiled questions must not be conflated with a joint `(F,Γ)` confidence region.

There is nevertheless a coverage qualification. At the physical null `F=0`, Γ is not identifiable and flux lies on a boundary, so the regular conditions behind the usual Wilks calibration are not all satisfied. [Cowan et al.](https://arxiv.org/abs/1007.1727) describes the relevant asymptotic boundary treatment, but exact coverage for this finite LAT stack should be established by Monte Carlo if the manuscript claims calibrated frequentist coverage.

The implementation also omits the physical null. `ul_ts` references each positive-flux row/profile to `ts_row.max()`. If every scanned positive-flux cell is below the true null, it incorrectly treats the least-bad finite cell as the maximum. Exact fix: include TS=0 at F=0 when forming the profile, use the physical maximum `max(0, max(scanned TS))`, require a valid crossing bracket, and separately validate the profile threshold by simulation.

### B7. Photon-to-energy-flux conversion — CORRECT

For an integral photon flux over 0.1–1000 GeV with spectrum proportional to `E^-Γ`, the normalization cancels and the requested 0.1–100 GeV energy flux is

```text
C100(Γ) = (erg per GeV)
          × ∫[0.1,100] E^(1−Γ) dE
          / ∫[0.1,1000] E^(−Γ) dE.
```

Thus the formula in `cluster/collect_stack.py:44-50` is dimensionally and mathematically correct. Independent analytic and 20,001-point log-grid calculations gave:

| Γ | analytic `C100` (erg/ph) | code-style trapz | relative error |
|---:|---:|---:|---:|
| 1.0 | 1.73761005062e-2 | 1.73760998920e-2 | −3.53e-8 |
| 1.5 | 4.95532203191e-3 | 4.95532176918e-3 | −5.30e-8 |
| 2.0 | 1.10673306900e-3 | 1.10673299076e-3 | −7.07e-8 |
| 2.5 | 4.65402558968e-4 | 4.65402517843e-4 | −8.84e-8 |
| 4.0 | 2.40299759700e-4 | 2.40299725726e-4 | −1.41e-7 |

At Γ=2, the numerator is `ln(100/0.1) = ln(1000) = 6.90775527898`; the denominator is `1/0.1 − 1/1000 = 9.999`. At Γ=1, the numerator is 99.9 and the denominator is `ln(1000/0.1) = ln(10000)`. Γ=4 is also finite; neither grid endpoint is singular for these finite nonzero bounds.

The numerical integration is converged far beyond the precision plausibly quoted for the limits. The only small issue is the rounded `1.602e-3` erg/GeV. From the exact SI elementary charge, the exact value is `1.602176634e-3`, so all converted values are low by about 0.011025%. See [NIST, elementary charge](https://physics.nist.gov/cgi-bin/cuu/Value?e). Either retain the rounded constant and quote commensurate precision, or use the exact conversion.

### B8. Grid agreement — CORRECT as shipped, but insufficiently guarded

The two definitions are numerically registered in the pinned NumPy behavior:

- index: both are the 31 values 1.0, 1.1, …, 4.0;
- flux: `np.logspace(-11,-3,80)` is exactly equal element-for-element to `10**np.linspace(-11,-3,80,endpoint=True)` in the environment tested;
- both endpoints are included;
- the logarithmic step is `8/79 = 0.1012658227848` dex, a ratio of `1.262600109875` between adjacent flux values.

This matches `Stack.py:221-243` and `collect_stack.py:39-40`. See the [NumPy 1.26 `logspace` definition](https://numpy.org/doc/1.26/reference/generated/numpy.logspace.html).

The shape assertion catches a bin-count change but not a same-shaped axis change. Exact hardening: save the actual index and flux axes with every per-event surface, hash them, and require exact equality at collection and ingest. Avoid separately hardcoding them in three producers/consumers.

## C. GUARDS

### C9. `assert_data_covers` — DOES NOT HOLD

`cluster/run_task.py:63-75` extracts only `k[-1]` from a `DSTYP*` keyword. It therefore maps `DSTYP11` to `DSVAL1`, not `DSVAL11`, and `DSTYP10` to `DSVAL0`. The same defective primitive is duplicated in `cluster/make_cones_from_weekly.py:61-73` and `cluster/download_ft1_1tev.py:34-44`.

A concrete false pass is:

```text
DSTYP1  = TIME
DSVAL1  = 0:800000000
DSTYP11 = ENERGY
DSVAL11 = 100:100000
```

The actual energy ceiling is 100 GeV, but the guard reads the upper end of `DSVAL1` (800,000,000), sees it above 1,000,000, and passes. If no `DSTYP* == ENERGY` is present, the loop simply ends and the function also passes. This violates the fail-loud invariant. The FSSC DSS format explicitly uses a numbered `DSTYPj`/`DSVALj` family; see [FSSC DSS keyword specification](https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/dss_keywords.html).

The guard additionally ignores `DSUNI`, does not convert units, validates only the upper bound, and assumes a simple colon grammar.

Exact fix: match `^DSTYP(\d+)$`, retain the full numeric suffix, require exactly one usable ENERGY selection (or normalize multiple compatible entries), parse its full DSS expression, validate/convert `DSUNI`, and require both lower and upper coverage. A missing or unparseable ENERGY reference must raise. Factor this into one tested helper used by all three scripts. For an operational independent check, run `gtvcut infile=<FT1> table=EVENTS suppress_gtis=yes` and compare normalized cuts.

### C10. Provenance — DOES NOT HOLD end to end

The task-side content hash is materially better than the former hardcoded literal. In the normal `run_task.py` path, the vendored directory is put first on `sys.path`, the package is imported, and `fingerprint()` hashes that imported package. If a task stamps `pipeline_sha256: unavailable`, `ingest_cluster_results.py:114-123` will normally reject it because it cannot equal the local expected digest. Thus the specific statement that task-side `unavailable` automatically passes is false.

The end-to-end claim still fails:

- `cluster/provenance.py:26-42` prefers any importable `fermi_stacking`. `collect_stack.py` never runs that package, yet importing an unrelated site-installed upstream copy succeeds and stamps its hash into the stack. Conversely, falling back to the vendored copy says what was nearby, not necessarily what made each input array.
- `cluster/ingest_cluster_results.py:133-150` never checks the stack JSON's `pipeline_sha256` at all.
- The stack JSON is optional: if it is absent, the convention/provenance checks are skipped.
- The expected hash may be redirected by `FS_PIPELINE_DIR`; it is not bound to an owner-controlled release manifest.
- The digest covers only `fermi_stacking/**/*.py`. It excludes the cluster drivers, frozen configuration, environment/builds, catalogs, FT1/FT2, diffuse models, source catalog, and the collector whose mathematics creates the returned stack.
- `pipeline_path` is recorded but never checked against the loaded module location.

Exact fix: at task start, resolve `fermi_stacking.__file__`, require it to be beneath the configured vendored root, and hash that explicit path. Create an owner-signed/owner-controlled release manifest covering the vendored fork, every driver, frozen analysis block, environment lock, catalog, and reference-data hashes. Have every task record its full input/product manifest. Have the collector hash its own code and verify all task digests before stacking. Require and validate the six stack manifests and bind each to its NPZ by SHA-256. The return-side comparison must use the independent owner manifest, not a caller-selectable nearby tree.

### C11. Scheduler wrappers and mutable manifest — DOES NOT HOLD

Under `set -euo pipefail`, exit 3 from `run_task.py` is the wrapper's nonzero exit, so both schedulers mark the array element failed. In SLURM, `sacct` retains `ExitCode=3:0`, which distinguishes it from exit 1 if someone inspects the code, but the coarse state is `FAILED` for both. See [SLURM job exit codes](https://slurm.schedmd.com/job_exit_code.html).

Nothing downstream correctly consumes that distinction. A recorded no-data/zero-exposure skip writes no `.npy` and no `task_meta.json`; `make_manifest.py` therefore resubmits it forever, while ingest requires 84 metadata files. The documented “normal skip” convention is not represented in the completion model.

The array mapping has a separate race. `submit_slurm.sh:23` and `submit_pbs.sh:23` read the live shared `tasks.txt` only when each worker starts. `make_manifest.py:31-37` rewrites that file and removes completed tasks. Example: submit lines `[A,B,C]`; A finishes; regenerate to `[B,C]`; the pending old index 2 now executes C and old index 3 reads an empty line. Jobs do not retain the task identity they were submitted for. Duplicate execution of the same run directory is then possible.

Exact fix:

1. Give every submission an immutable, uniquely named manifest; pass its absolute path to the job and never rewrite it while the array exists.
2. Require a nonempty line with exactly a known `(event,window)` identity before running.
3. Write an atomic terminal record for every outcome: success, legitimate skip, or failure. Include identity, hashes, and reason. Teach manifest generation and ingest to understand those explicit states.
4. Map an intentional skip to scheduler success only after the skip record is durably written; preserve the scientific status inside that record.
5. Use a per-task lock/attempt directory so stale arrays cannot concurrently mutate one run directory.

Additional scheduler portability defects are loud but immediate: SLURM/PBS output paths are opened by the scheduler before the script's `mkdir -p logs`, so `cluster/logs` must exist before submission; the PBS script uses Torque-style `-t`, `PBS_ARRAYID`, and `nodes=1:ppn=4`, while PBS Pro sites commonly use `-J`, `PBS_ARRAY_INDEX`, and `select`/`ncpus`/`mem`; the PBS resource request contains no 8 GB memory request; and both wrappers assume conda under exactly `~/miniconda3` or `~/anaconda3`. Supply separately tested site profiles rather than one nominally portable PBS wrapper.

## D. REPRODUCIBILITY

### D12. Weekly cones versus FSSC cones — NOT CONFIRMED; false as shipped

#### Fixed mission stop silently truncates one required window

Both cone paths share a hardcoded stop of `797361626`:

- `cluster/make_cones_from_weekly.py:54,145-148`;
- `cluster/download_ft1_1tev.py:26,51`.

For `AT2026dbl`, `sample/fbot_catalog_tiered.csv:15` gives `t0 = 792750185`. The requested post-10 Ms stop is `802750185`, but staging ends at `797361626`:

```text
requested post-t0 span     10,000,000 s
staged post-t0 span         4,611,441 s = 53.3732 d
missing span                5,388,559 s = 62.3676 d
staged fraction             0.4611441 = 46.11441%
```

The current official archive contains weekly photon files through the requested endpoint and beyond; see the [HEASARC LAT weekly photon directory](https://heasarc.gsfc.nasa.gov/FTP/fermi/data/lat/weekly/photon/). This is a stale constant, not an unavoidable future-mission boundary.

`run_task.py:88-90,135-136,206` still requests and records the full interval. Its only FT1 invariant is energy coverage; it has no time/GTI or FT2 coverage check. A partial-window result can therefore be labelled `post_1e7` and look plausible. Existing cone cache entries survive because `make_cones_from_weekly.py:142-143` checks only the energy ceiling.

Exact fix: remove both fixed stop constants. Derive interval coverage from the validated weekly-file union and FT2 GTIs; require full coverage of every requested task or fail loudly. Add a run-time FT1-GTI/FT2 coverage invariant for the exact task interval. Invalidate and rebuild cached cones, especially `AT2026dbl`.

#### The nominal cuts are close, not proven identical

Conditional on a complete, unmodified official weekly Photon mirror, both routes intend a 30-degree cone, `t0 ± 10^7 s`, 100–1,000,000 MeV, and no **additional** event-class/type cut. Official weekly Photon files are already SOURCE-class-or-better products; `evclass=INDEF evtype=INDEF` does not mean raw all-class data. See [FSSC weekly-file guidance](https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/LAT_weekly_allsky.html).

Differences remain:

- the FSSC request serializes RA/Dec to five decimals (`download_ft1_1tev.py:53`), the weekly route to six (`make_cones_from_weekly.py:169`), and downstream uses the catalog floats. Across the 14 selected events, the two query centers differ by up to about 0.022396 arcsec. Tiny scientifically, but enough to disprove exact membership at a 30-degree boundary and contrary to the documented need for consistent cone centers;
- weekly selection explicitly writes `zmax=180`; the FSSC form does not expose that same step, so DSS/history need not be byte-equivalent;
- FSSC can return multiple PH files, while the weekly route writes one merged file;
- neither route compares normalized DSS/GTI/class/Pass/reprocessing invariants.

The correct claim is “intended membership-equivalent after validation,” not byte-equivalent or indistinguishable by invariants.

#### The overlap optimization is correct at normal edges, unsafe on invalid metadata

`weeks_overlapping()` uses `ts <= tmax and te >= tmin`, so a weekly file that straddles or exactly touches either boundary is retained. This is conservative; `gtselect` makes the final event cut. Missing/unreadable headers are also retained, as intended.

But `float('nan')` is accepted in `weekly_time_index`, comparisons with NaN are false, and the file is silently dropped. Reversed/nonfinite intervals can also be dropped. A NaN in the primary header prevents trying a valid EVENTS header and is cached as nonstandard JSON `NaN`.

Exact fix: require finite `TSTART/TSTOP` with `TSTART <= TSTOP`, compare primary and EVENTS values, and treat invalid metadata as fail-loud or conservatively unknown. Serialize cache JSON with `allow_nan=False`.

#### Mirror completeness and portability are not guarded

- The default `--pattern '*PH*.fits'` at `make_cones_from_weekly.py:188` does not match official lowercase names such as `lat_photon_weekly_w940_p305_v001.fits` on case-sensitive Linux. Phase 1 therefore fails loudly with the documented command unless the collaborator supplies an unmentioned pattern.
- The code never requires exactly one approved version per mission week. Missing weeks create silent gaps; duplicate versions can duplicate events; mixed reprocessing releases are accepted.
- The cache stamp is only `size:int(mtime)`, so replacements can retain stale times.
- If the selected subset is empty, the function silently falls back to the full list instead of diagnosing uncovered time.
- Relative input paths can be written before changing `cwd` to the event directory.
- `shell=True` with an unquoted command makes spaces/metacharacters in either site's paths significant.
- FSSC resumability declares an event complete if any one `*_PH*.fits` has a 1 TeV ceiling; an interrupted multipart download can therefore be accepted as complete.

Exact fix: enumerate and validate official lowercase filenames with a release-aware regex; require one approved file per week and a gap-free finite interval union; hash the selected inputs; resolve all paths; invoke `gtselect` with an argument vector and `shell=False`; fingerprint every cone's coordinates/time/energy/class/type/input inventory; and use an atomic multipart completion manifest.

### D13. Timing gate and task count — CONFIRMED

`min_window_s` is the minimum eligible window duration for the event's timing quality. The code skips when `dur < min_window_s`, so equality is included. That is the correct inequality.

Independent recomputation from `sample/fbot_catalog_tiered.csv` and configured tiers G1/G2 gives:

```text
selected events        14 = 13 G1 + 1 G2
CSS161010 minimum       100000 s (day timing)
other 13 minima         10 s (subday timing)
eligible events/window 14 for each of the six windows
initial manifest rows   84
duplicate names         0
```

CSS161010 is included at equality for the 100 ks windows. A resumed manifest intentionally contains fewer rows because completed `.npy` paths are omitted. No inequality/count change is needed.

This confirms 84 intended task identities, not 84 complete science intervals: because of D12, the shipped staging logic currently describes 83 full requested intervals plus one truncated interval.

## FINDINGS RANKED

The ranking below puts silent wrong science first, then failures likely to become loud, then lower-severity/portability issues. Each fix is a prerequisite or hardening action; none was applied during this audit.

### Silent wrong science

#### 1. Component-0 livetime cube is reused for all bands — CRITICAL

- **Location:** `Preprocess.py:637-644`; `run_task.py:196-199`; `Stack.py:214-218`.
- **Break:** 95/105-degree component data and maps are paired with the 85-degree ltcube in null and scan likelihoods, corrupting exposure/response while still producing plausible surfaces.
- **Exact fix:** use and validate `ltcube_00`, `ltcube_01`, `ltcube_02` locally per component in every likelihood construction; remove the singleton assignment; assert selection agreement.

#### 2. D04 nearby-source freedom is a silent no-op — CRITICAL

- **Location:** `Preprocess.py:64-101` (notably 79); `Stack.py:50-87` (notably 65).
- **Break:** both helpers use regexes that require `name="RA"` immediately followed by `value=...` (and likewise DEC). Standard Fermi XML contains intervening attributes, e.g. `name="RA" scale="1.0" value="83.45"`; see the official [FSSC XML model examples](https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/xml_model_defs.html). No positions are parsed, the helper returns silently, and every catalog source remains frozen after callers freeze all parameters. The adopted 2-degree freedom is not executed.
- **Exact fix:** parse XML with `ElementTree`, read attributes by name, apply `scale`, compute true spherical separation, and require the parsed/freed source set to match an independently constructed expectation. Zero parsed positions must fail loudly.

#### 3. `AT2026dbl post_1e7` is silently truncated — CRITICAL

- **Location:** `make_cones_from_weekly.py:54,142-148`; `download_ft1_1tev.py:26,49-51`; absence of time guard in `run_task.py:63-75`.
- **Break:** only 4,611,441 of the requested 10,000,000 post-t0 seconds are staged, but task metadata records the full interval.
- **Exact fix:** derive and require full FT1/FT2/GTI coverage from actual inputs; remove fixed stop; invalidate/rebuild the cached cone; stamp verified coverage.

#### 4. Collector/ingest do not enforce the authoritative 84 identities — CRITICAL

- **Location:** `collect_stack.py:80-97`; `ingest_cluster_results.py:95-103,106-150`.
- **Break:** collection stacks every matching file present, including a one-event partial stack or stale/extra runs. Ingest counts 84 metadata files but not unique `(event,window)` identities, checks only the lexicographically first stack per window, treats stack JSON as optional, and does not compare NPZ/JSON membership. Eighty-four duplicate metadata objects plus six arbitrary 31×80 NPZs and no JSON can satisfy the implemented gates.
- **Exact fix:** derive one authoritative expected identity set; require exact set equality and count one for tasks/successes/skips; reject extra/missing/duplicate events; require exactly one NPZ/JSON pair per window; store the per-event cube and independently recompute the sum at ingest.

#### 5. Optimizer failures can define an upper limit — CRITICAL/HIGH

- **Location:** quality claim at `collect_stack.py:17-18`; recorded but discarded values at `Stack.py:273-275`; no quality logic in `collect_stack.py:80-117`.
- **Break:** MINUIT quality and return code exist for every scan cell but never enter the saved surface/collector. A synthetic single bad cell changed a smooth approximately `10^-7` crossing to approximately `9.8×10^-9`, a factor of ten too deep, while the code would report it normally.
- **Exact fix:** retain aligned component/event quality and status arrays; require acceptable convergence at the peak and both crossing-bracket cells; reject nonmonotonic rebounds/multiple crossings; persist and ingest a verified quality record.

#### 6. A missing energy component can produce a completed surface — HIGH

- **Location:** `run_task.py:201-205`; `Stack.py:443-526`.
- **Break:** file count substitutes for exact identity, allowing a plausible two-band result if the trailing component is missing.
- **Exact fix:** require complete exact artifact sets for IDs 0,1,2 and make `combine_likelihood` reject all other sets.

#### 7. Already-null-referenced TS is re-referenced at finite flux — HIGH for the profiled/2-D result

- **Location:** `Stack.py:487-526`; `collect_stack.py:95`.
- **Break:** subtracts `Σ TS(Γ,10^-11)` from an already null-relative stack. Fixed-Γ crossings cancel row constants, but the Γ-profile and 2-D surface can change.
- **Exact fix:** sum the saved TS directly and include an explicit physical-null point/likelihood in the data model.

#### 8. Nonfinite/bad surfaces pass structural validation — HIGH

- **Location:** `collect_stack.py:92-103`; `ingest_cluster_results.py:137-150`.
- **Break:** shape is checked but real numeric dtype and `isfinite` are not. NaN can poison `max/argmax`; an unbracketed result becomes `Infinity`, which Python writes although [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259#section-6) does not permit it in JSON.
- **Exact fix:** require real finite axes and arrays at task, collection, and ingest; treat unbracketed UL as failed or encode `null` with explicit status; serialize with `allow_nan=False`.

#### 9. Staged isotropic files are bypassed by bare component basenames — HIGH portability

- **Location:** component dictionaries at `run_task.py:36-43` override the absolute root `isodiff` generated at `run_task.py:147-149`.
- **Break:** Fermipy resolves bare isotropic names through each site's environment/search paths. Two sites can use different copies or one can fail, despite staging the audited files under `refdata`.
- **Exact fix:** configure absolute paths for all three component isotropic templates and hash the resolved files in every task record.

#### 10. Weekly mirror completeness/version is not an invariant — HIGH cross-site risk

- **Location:** `make_cones_from_weekly.py:76-134,151-159,188-205`.
- **Break:** missing weeks silently remove data; duplicate versions can duplicate photons; mixed releases differ by site; NaN time metadata can silently exclude a file; weak cache identity preserves stale indexing.
- **Exact fix:** validate a release-aware one-file-per-week inventory and gap-free time union, finite headers, Pass/processing identity, and input hashes before cone generation.

#### 11. Stack products are not cryptographically or atomically paired — HIGH

- **Location:** `collect_stack.py:115-117`; `ingest_cluster_results.py:133-150`.
- **Break:** NPZ is written before JSON directly to final names; interruption/concurrent collectors can leave a mismatched pair. Ingest neither requires the JSON nor hashes the NPZ, validates axes/events, or recomputes reported ULs.
- **Exact fix:** write unique temporary products, record NPZ SHA-256 and generation ID, atomically publish a completion record last, lock per window, and independently recompute all manifest scalars at ingest.

#### 12. Provenance excludes the code and inputs that determine the returned number — HIGH

- **Location:** `provenance.py:26-60,76-90`; `collect_stack.py:99-117`; `ingest_cluster_results.py:114-150`.
- **Break:** a task hash can certify the fork but not drivers/configuration/data; a collector can stamp an unrelated import; stack provenance is never gated.
- **Exact fix:** use an owner-controlled full release/input manifest, assert loaded paths, bind each product to hashes, and validate all layers at ingest.

### Loud failures or operational loss

#### 13. Legitimate skips are scheduler failures and never become complete identities — HIGH operational

- **Location:** `submit_slurm.sh:13,27`; `submit_pbs.sh:11,27`; `run_task.py:97-101`; `make_manifest.py:31-34`.
- **Break:** exit 3 appears as scheduler `FAILED`, is resubmitted forever, and leaves the final 84-meta ingest impossible. Exit code inspection can distinguish 3 from 1, but unattended status cannot.
- **Exact fix:** write a durable skip record, translate only that verified outcome to wrapper exit 0, and make manifest/collector/ingest consume explicit task states.

#### 14. Regenerating `tasks.txt` retargets queued array indices — HIGH operational

- **Location:** `make_manifest.py:31-37`; `submit_slurm.sh:23-27`; `submit_pbs.sh:22-27`.
- **Break:** pending jobs read a rewritten line mapping and may execute duplicates, wrong tasks, or empty identities into shared run directories.
- **Exact fix:** immutable per-submission manifests with absolute paths, identity validation, attempt directories, and task locks.

#### 15. `.npy` existence is an unsafe completion sentinel — HIGH operational/science handoff

- **Location:** `run_task.py:92-94,206-210`; `make_manifest.py:31-34`; surface write at `Stack.py:526`.
- **Break:** a kill after `.npy` but before `task_meta.json` makes resubmission skip the task forever; collection can consume the orphan.
- **Exact fix:** validate and hash outputs, atomically write metadata, then publish a terminal completion record last; discover only validated records.

#### 16. Default weekly glob matches no official Linux filenames — HIGH portability, loud

- **Location:** `make_cones_from_weekly.py:188-201`.
- **Break:** default `*PH*.fits` does not match lowercase `lat_photon_weekly_...fits` on a case-sensitive cluster, so the documented phase-1 command exits immediately.
- **Exact fix:** default to an anchored official lowercase, release-aware pattern or require the site to declare and validate its inventory pattern.

#### 17. PBS/SLURM/conda/log assumptions are not site portable — MEDIUM/HIGH operational

- **Location:** `submit_slurm.sh:3,14,20`; `submit_pbs.sh:4-7,13,19,22`.
- **Break:** pre-job log directory timing, Torque versus PBS Pro syntax/resources, missing PBS memory request, and two hardcoded conda installation layouts can fail differently at the two sites.
- **Exact fix:** create logs before submission and provide scheduler/site-specific audited wrappers with explicit CPU/memory, array variable, conda initialization, working directory, and immutable manifest.

#### 18. Forced Tk GUI backend can fail on headless compute nodes — MEDIUM, loud

- **Location:** `Preprocess.py:24`; `Stack.py:10`.
- **Break:** `TkAgg` requires Tk/display support that batch nodes commonly lack. The documented `\m` warning is unrelated.
- **Exact fix:** use the noninteractive `Agg` backend for batch code or make backend selection an explicit tested site setting.

### Lower-severity numerical/reporting issues

#### 19. Crossing interpolation has percent-level phase bias — LOW/MEDIUM

- **Location:** `collect_stack.py:53-62`.
- **Break:** linear interpolation in log-flux is not exact for a profile locally quadratic in linear flux. For `q(F)=2.71(F/10^-8)^2`, the exact crossing `10^-8` is returned as `9.87148665×10^-9`, 1.285% low; the phase scan reached about 1.35%.
- **Exact fix:** adaptively refine the likelihood around the crossing, or return the enclosing bracket and a quantified discretization uncertainty validated on synthetic curves.

#### 20. Environment and reference inputs are versioned weakly for two-site identity — MEDIUM reproducibility

- **Location:** `cluster/environment.yml`; `cluster/cluster_config.yaml`; task metadata fields in `run_task.py:206-210`.
- **Break:** core versions are pinned but solver builds/transitive dependencies are not locked, and FT1/FT2/catalog/diffuse/source-catalog hashes are not stamped. Two successful sites can therefore execute different binaries or inputs.
- **Exact fix:** generate an explicit platform lock/spec for each cluster, record package build strings, and hash every science input. Compare those manifests before comparing surfaces. See [Conda environment export guidance](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html).

## COULD NOT VERIFY

1. **Actual Fermitools behavior for a task whose requested `tmax` exceeds staged FT1/GTI coverage.** Repository code does not prevent a partial result, but Fermitools 2.2 was unavailable here. Decisive command sequence on a cluster:

   ```bash
   gtvcut infile=data/ft1_1tev/AT2026dbl/AT2026dbl_PH00.fits table=EVENTS suppress_gtis=yes
   python cluster/run_task.py --config cluster/cluster_config.yaml --event AT2026dbl --window post_1e7
   # Then inspect EVENTS/GTI and ltcube TSTART/TSTOP against 792750185:802750185.
   ```

   A completed likelihood whose coverage ends near `797361626` confirms the silent partial-window path; a loud tool failure is safer but still stop-ship.

2. **Exact FSSC-versus-weekly event membership and normalized DSS ordering.** The selections are close but not byte-identical and local mirror identity is unknown. Decisive test: create both cones for one event, run the exact downstream selections, compare unique `(RUN_ID,EVENT_ID)` sets, run `gtvcut` on both, and compare normalized DSS plus GTIs. Repeat for `AT2026dbl` with current weeks.

3. **Numerical magnitude of the finite-flux re-reference error on campaign data.** No completed surfaces are present. Decisive standalone command after return:

   ```bash
   python - <<'PY'
   import glob, numpy as np
   a = [np.load(p) for p in glob.glob('runs/*/Add_Stacking/Numpy_Arrays/*.npy')]
   first = np.stack([x[:, 0] for x in a])
   s = first.sum(axis=0)
   print('per-event first-column min/max:', first.min(), first.max())
   print('summed row-offset min/max/ptp:', s.min(), s.max(), np.ptp(s))
   PY
   ```

4. **Exact frequentist coverage of the profiled 2.71 rule at the flux boundary with Γ unidentified under the null.** The asymptotic one-parameter threshold is correct; exact coverage needs injection/null Monte Carlo through the frozen pipeline. The settling test is a predeclared ensemble at known fluxes, extracting limits exactly as the campaign does and measuring coverage versus 95%.

5. **Optimizer reliability of real scan cells.** The fork records quality/status, but the available `.npy` format discards them. The settling command is to parse all `Output_*.txt` scan records, align them with `(component,Γ,F)`, and require quality 3/status 0 around every peak and crossing before accepting any surface.

6. **Whether both remote sites will resolve identical binaries, isotropic models, extended-source templates, FT2, and weekly photons.** Nothing returned by the current package proves this. Settle it before submission with an explicit SHA-256 manifest of resolved executables/package builds and all science inputs, then compare manifests byte for byte.

7. **Repository identity.** The brief prohibited Git operations, so I did not independently execute `git rev-parse` or compare the working tree with public HEAD `0c46460`. The audit scope uses the brief's assertion that this tree is the artefact of record.

## Independent judgement

*Finally, your own independent judgement: anything wrong or fragile that this brief did not ask about.*

The most serious independent discovery is the D04 parser failure: the code added specifically to free catalog sources within 2 degrees does nothing on the standard XML attribute order and fails open. This belongs beside the ltcube reuse and truncated window as a primary stop-ship item.

The second is that the collector's own docstring promises optimizer-quality gating that does not exist. This is unusually dangerous because it creates false confidence: the fork already emits the evidence needed to reject bad cells, yet the final surface discards it. The first-crossing algorithm is especially vulnerable to a single downward optimizer excursion.

Third, the campaign lacks one authoritative, immutable identity/provenance chain. Task discovery, completion, collection, and ingest each infer state independently from globs/counts/existence. That design explains several defects at once: two-component completion, orphan `.npy` acceptance, partial stacks, duplicate event identities, optional JSON, and mutable array mappings. The durable repair is not another count assertion; it is one immutable 84-identity manifest, atomic per-task terminal records, exact-set collection, and independent ingest recomputation.

Other fragilities worth fixing before either deployment:

- `run_task.py` has no per-task `PFILES` sandbox even though the cone builder correctly creates one. Fermitools parameter files retain mutable state; concurrent array jobs sharing defaults can race or inherit site/user values. Set a unique `PFILES=<run>/pfiles;<system-pfiles>` before importing/running the tools and record it.
- Bare component isotropic names and unresolved extended-source templates defeat the otherwise sensible staging of `refdata`; resolve and hash every file actually opened.
- Add a dedicated two-site comparison mode. Never unpack both returns under one tree and let `ingest_cluster_results.py` choose the lexicographically first product. Compare exact membership/config/input manifests first, then cellwise surfaces and independently recomputed limits.
- Do not let a successful rerun overwrite or coexist ambiguously with an older attempt under the same directory. Preserve immutable attempt IDs and choose a certified attempt explicitly; this respects the rule never to delete `runs/` while preventing stale data from being globbed into science.
- Treat every configuration helper that cannot find its reference as a hard error. The broken ENERGY and XML guards share the same failure pattern: “not found” is interpreted as “nothing to do.”

Independent bottom line: do not spend either allocation until the three adopted-analysis defects (per-component ltcubes, D04 source freeing, full `AT2026dbl` time coverage) are fixed and regression-tested, and until task/stack identity plus optimizer-quality gates fail closed. After fixes, perform one deliberately small end-to-end smoke task at each site, compare normalized cuts/resolved inputs/component products, and only then release the 84-task arrays.
