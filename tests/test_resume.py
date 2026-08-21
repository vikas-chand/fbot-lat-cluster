"""Equivalence test: does a killed-and-resumed run_stacking produce exactly the
same rows as an uninterrupted one?"""
import os, sys, shutil, warnings, json
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs; stubs._install()
FORK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Fermi_Stacking_Analysis')
sys.path.insert(0, FORK)
from fermi_stacking.stacking.Stack import MakeStack
from fermi_stacking import resume as R

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resume_test')
EVENT, PSF, NFLUX = 'AT2018cow', 2, 80

def _inputs():
  return dict(
    ft1='none', ft2='none', galdiff='none', isodiff='none', ltcube='None',
    irfs='P8R3_SOURCE_V3', emin=100.0, emax=1000000.0, tmin=0.0, tmax=1.0,
    zmax=90.0, evclass=128, evtype=3, index_min=1.0, index_max=4.0,
    flux_min=-11.0, flux_max=-3.0, num_flux_bins=NFLUX, run_name='test',
    use_scratch=False, scratch='None', delete_4fgl=False,
    alpha_low=0.0, alpha_high=1.0, alpha_step=0.1,
    beta_low=0.0, beta_high=1.0, beta_step=0.1,
    JLA=True, sample_file=os.path.join(ROOT, 'sample.csv'), file_type='csv', column_name='name',
    column_ra='ra', column_dec='dec', run_list='default', psf_low=0, psf_high=4,
    job_type='s', submission_type='array', sample_name_list=[EVENT],
    show_plots=False, calc_sed=False, sed_logEbins=[2.0, 3.0], path='none',
    ROI_RA=0.0, ROI_DEC=0.0, ROI_radius=10.0, binsz=0.1, coordsys='CEL',
    enumbins=20, nxpix=100, nypix=100, proj='AIT', xref=0.0, yref=0.0,
    reduced_x=50, reduced_y=50,
)

def build_root():
    shutil.rmtree(ROOT, ignore_errors=True)
    out = os.path.join(ROOT, 'Preprocessed_Sources', EVENT, 'output')
    os.makedirs(out)
    for j in range(3):
        for n in ('srcmap_0%d.fits' % j, 'bexpmap_0%d.fits' % j):
            open(os.path.join(out, n), 'wb').write(b'\0' * 2880 * 3)
        open(os.path.join(out, 'fit_model_3_0%d.xml' % j), 'w').write('<source_library/>')
        open(os.path.join(out, 'null_likelihood_%d.txt' % j), 'w').write('-1000.0\n')
    open(os.path.join(out, 'ltcube_00.fits'), 'wb').write(b'\0' * 2880 * 3)
    with open(os.path.join(ROOT, 'sample.csv'), 'w') as f:
        f.write('name,ra,dec\n%s,244.0,22.27\n' % EVENT)
    import yaml
    with open(os.path.join(ROOT, 'inputs.yaml'), 'w') as f:
        yaml.safe_dump(_inputs(), f)
    return out

def make_inst():
    inst = MakeStack(os.path.join(ROOT, 'inputs.yaml'))
    inst.home = ROOT
    inst.JLA = True
    inst.sample_name_list = [EVENT]
    inst.ltcube = os.path.join(ROOT, 'Preprocessed_Sources', EVENT, 'output', 'ltcube_00.fits')
    return inst

def rowdir():
    return os.path.join(ROOT, 'Stacked_Sources', 'Likelihood_%d' % PSF, EVENT)

def snapshot():
    d = rowdir()
    return {f: open(os.path.join(d, f)).read()
            for f in sorted(os.listdir(d)) if f.endswith('.txt')}

# ---------------------------------------------------------------- run A
build_root(); os.chdir(ROOT)
make_inst().run_stacking(EVENT, PSF)
full = snapshot()
print('RUN A (uninterrupted): %d row files' % len(full))

# ---------------------------------------------------------------- run B
build_root(); os.chdir(ROOT)
KILL_AFTER = 12
import fermi_stacking.resume as _R
_orig = _R.write_row_atomic
count = {'n': 0}
def killing_write(path, text):
    if count['n'] >= KILL_AFTER:
        raise KeyboardInterrupt('simulated SIGKILL at row %d' % count['n'])
    count['n'] += 1
    _orig(path, text)
# patch the name Stack.py actually calls through
import fermi_stacking.stacking.Stack as S
S._fs_resume.write_row_atomic = killing_write
try:
    make_inst().run_stacking(EVENT, PSF)
except KeyboardInterrupt as e:
    print('RUN B: killed ->', e)
partial = snapshot()
print('RUN B after kill: %d row files' % len(partial))

S._fs_resume.write_row_atomic = _orig
os.chdir(ROOT)
make_inst().run_stacking(EVENT, PSF)
resumed = snapshot()
print('RUN B after resume: %d row files' % len(resumed))

# ---------------------------------------------------------------- verdict
print()
same_names = set(full) == set(resumed)
diffs = [f for f in sorted(set(full) & set(resumed)) if full[f] != resumed[f]]
print('same set of row files :', same_names)
print('rows differing        :', len(diffs))
print('rows preserved+skipped:', len(partial))
ok = same_names and not diffs and len(full) == 31
print()
print('VERDICT:', 'PASS - resumed run is byte-identical to uninterrupted run' if ok else 'FAIL')
sys.exit(0 if ok else 1)
