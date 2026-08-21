"""Adversarial: try to make a BAD preserved row survive the resume guards."""
import os, sys, shutil, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs; stubs._install()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Fermi_Stacking_Analysis'))
from fermi_stacking import resume as R

T = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'guard_test')
shutil.rmtree(T, ignore_errors=True); os.makedirs(T)
NF = 80

def good_row(idx):
    return '\n'.join('\t'.join(['1.00e-09', '%.1f' % idx, '-1234.5000000000',
                                '3', '0']) for _ in range(NF))

def check(name, path, idx, expect):
    got = R.row_is_complete(path, NF, idx)
    ok = (got == expect)
    print(('  PASS ' if ok else '  FAIL ') + name + ('  (accepted)' if got else '  (rejected)'))
    return ok

results = []
p = os.path.join(T, 'r.txt')

open(p, 'w').write(good_row(2.0))
results.append(check('complete row accepted', p, 2.0, True))

open(p, 'w').write('\n'.join(good_row(2.0).split('\n')[:43]))
results.append(check('row truncated at LINE boundary rejected', p, 2.0, False))

open(p, 'w').write('\n'.join(good_row(2.0).split('\n')[:43]) + '\n1.00e-09\t2.0\t-12')
results.append(check('row truncated MID-LINE rejected', p, 2.0, False))

open(p, 'w').write(good_row(2.0))
results.append(check('row carrying the WRONG index stamp rejected', p, 3.7, False))

open(p, 'w').write('')
results.append(check('empty row rejected', p, 2.0, False))

open(p, 'w').write('\n'.join(good_row(2.0).split('\n')[:79] + ['nan\t2.0\tnan\t3\t0']))
results.append(check('row with NaN fields rejected', p, 2.0, False))

results.append(check('absent row rejected', os.path.join(T, 'nope.txt'), 2.0, False))

print()
print('component discovery:')
sd = os.path.join(T, 'Stacked_Sources'); os.makedirs(sd)
for n in ('Likelihood_0', 'Likelihood_1', 'Likelihood_2'):
    os.makedirs(os.path.join(sd, n))
open(os.path.join(sd, 'Likelihood_0.done'), 'w').write('x')      # stray FILE
os.makedirs(os.path.join(sd, 'Likelihood_notanint'))              # bad suffix
got = [j for j, _ in R.component_dirs(sd)]
ok = got == [0, 1, 2]
print(('  PASS ' if ok else '  FAIL ') + 'stray file + bad suffix ignored -> %s' % got)
results.append(ok)

os.makedirs(os.path.join(sd, 'Likelihood_3'))                     # stale 4th
got2 = [j for j, _ in R.component_dirs(sd)]
ok2 = got2 == [0, 1, 2, 3]
print(('  PASS ' if ok2 else '  FAIL ')
      + 'stale component IS surfaced (so run_task can refuse) -> %s' % got2)
results.append(ok2)

print()
print('preprocessing completeness:')
out = os.path.join(T, 'pp', 'output'); os.makedirs(out)
def mk(n, b=2880*3): open(os.path.join(out, n), 'wb').write(b'\0' * b)
for j in range(3):
    mk('srcmap_0%d.fits' % j); mk('bexpmap_0%d.fits' % j)
    open(os.path.join(out, 'fit_model_3_0%d.xml' % j), 'w').write('<x/>')
    open(os.path.join(out, 'null_likelihood_%d.txt' % j), 'w').write('-1000.0\n')
mk('ltcube_00.fits')
ppdir = os.path.join(T, 'pp')
r1 = R.preprocessing_complete(ppdir, 3); print(('  PASS ' if r1 else '  FAIL ') + 'complete dir accepted')
results.append(r1)

open(os.path.join(out, 'null_likelihood_2.txt'), 'w').write('')   # killed mid-write
r2 = not R.preprocessing_complete(ppdir, 3)
print(('  PASS ' if r2 else '  FAIL ') + '0-byte null_likelihood rejected')
results.append(r2)
open(os.path.join(out, 'null_likelihood_2.txt'), 'w').write('-1000.0\n')

mk('srcmap_01.fits', 1000)                                        # truncated FITS
r3 = not R.preprocessing_complete(ppdir, 3)
print(('  PASS ' if r3 else '  FAIL ') + 'truncated FITS (not a 2880 multiple) rejected')
results.append(r3)
mk('srcmap_01.fits')

mk('srcmap_03.fits')                                              # stale 4th component
r4 = not R.preprocessing_complete(ppdir, 3)
print(('  PASS ' if r4 else '  FAIL ') + 'stale extra component rejected')
results.append(r4)
os.remove(os.path.join(out, 'srcmap_03.fits'))

r5 = not R.preprocessing_complete(ppdir, 4)                       # asked for more than present
print(('  PASS ' if r5 else '  FAIL ') + 'missing component rejected')
results.append(r5)

print()
print('resume switch:')
os.environ['FS_RESUME'] = '0'
r6 = not R.enabled(); print(('  PASS ' if r6 else '  FAIL ') + 'FS_RESUME=0 disables resume')
results.append(r6); os.environ.pop('FS_RESUME')

print()
print('%d/%d guards behave correctly' % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
