# Tests

These exercise the **resume logic**, not the physics. The likelihood layer is
stubbed (`stubs.py` installs fake `pyLikelihood` / `BinnedAnalysis` / `gt_apps`
modules) so the real `run_stacking` control flow executes without fermitools
installed, with a deterministic log-likelihood so two runs must agree exactly.

```bash
python tests/test_resume.py    # killed-and-resumed run == uninterrupted run
python tests/test_guards.py    # every way a bad preserved row could survive
```

`test_resume.py` runs the scan uninterrupted, then again with a simulated kill
after 12 of 31 index rows, resumes, and requires the resulting row files to be
byte-identical to the uninterrupted run.

`test_guards.py` is the adversarial half: truncation at a line boundary and
mid-line, a wrong index stamp, an empty file, non-finite fields, stray
`Likelihood_*` files, a stale extra component, a 0-byte `null_likelihood`, a
truncated FITS, and the `FS_RESUME=0` escape hatch. It caught a real defect —
`float('nan')` parses, so a row of failed fits was passing as complete.

Run them after any change to `resume.py`, `Stack.py:run_stacking`, or
`Preprocess.py:run_preprocessing`.
