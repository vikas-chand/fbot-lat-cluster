"""Install fake fermitools modules so the REAL Stack.py can be imported and its
run_stacking control flow exercised without fermipy/pyLikelihood installed.

The likelihood value is a deterministic function of (index, flux) so that an
uninterrupted run and a resumed run must agree exactly if the resume logic is
correct.
"""
import sys, types, math

def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

class _Param:
    def __init__(self, v=1.0): self._v = v
    def setValue(self, v): self._v = v
    def getValue(self): return self._v
    def __getattr__(self, n):          # setFree/setBounds/setScale/...
        return lambda *a, **k: None

class _Spectrum:
    def __init__(self): self._p = {}
    def getParam(self, n): return self._p.setdefault(n, _Param())

class _Src:
    def __init__(self): self.funcs = {'Spectrum': _Spectrum()}

class _Model:
    def __init__(self): self._s = {}
    def __getitem__(self, k): return self._s.setdefault(k, _Src())
    @property
    def params(self): return [_Param() for _ in range(5)]

class _LogLike:
    def __init__(self, owner): self._o = owner
    def value(self): return self._o._value()
    def writeXml(self, path):
        with open(path, 'w') as f: f.write('<source_library/>\n')

class _BinnedAnalysis:
    """Deterministic stand-in: logLike depends only on the set index/flux."""
    def __init__(self, obs, xml, optimizer=None, config=None):
        self.model = _Model(); self.tol = 0.0
        self.logLike = _LogLike(self)
        self._idx = None; self._flux = None; self._srcname = 'SRC'
    def setSpectrum(self, name, kind):
        self._srcname = name
    def _value(self):
        i = self._idx if self._idx is not None else 2.0
        fl = self._flux if self._flux is not None else 1e-9
        return -1234.5 + 10.0*math.log10(fl) - 3.0*abs(i)
    def freeze(self, k): pass
    def syncSrcParams(self, *a, **k): pass
    def fit(self, **k):
        sp = self.model[self._srcname].funcs['Spectrum']
        self._idx = sp.getParam('Index').getValue()
        self._flux = sp.getParam('Integral').getValue()
    def __getitem__(self, k): return self.model[k]
    def __getattr__(self, n):
        return lambda *a, **k: None

def _install():
    # local scipy is newer than the cluster's; romberg was removed in 1.15
    import scipy.integrate as _si
    if not hasattr(_si, 'romberg'):
        _si.romberg = lambda *a, **k: 0.0
    pl = _mod('pyLikelihood', Minuit=lambda ll: _MinuitObj(),
              BinnedConfig=lambda **k: None)
    # fermitools' BinnedAnalysis does `import pyLikelihood as pyLike`, and
    # Stack.py picks up the name through `from BinnedAnalysis import *`
    _mod('BinnedAnalysis', BinnedObs=lambda **k: object(),
         BinnedAnalysis=_BinnedAnalysis, BinnedConfig=lambda **k: None,
         pyLike=pl)
    _mod('SummedLikelihood', SummedLikelihood=object)
    _mod('IntegralUpperLimit', calc_int=lambda *a, **k: (0, {}))
    _mod('UpperLimits', UpperLimits=object)
    class _App:
        def __getitem__(self, k): return None
        def __setitem__(self, k, v): pass
        def run(self, *a, **k): pass
    _mod('gt_apps', filter=_App(), maketime=_App(), expCube=_App(),
         expMap=_App(), counts_map=_App(), srcMaps=_App(), diffResps=_App(),
         evtbin=_App(), gtexpcube2=_App())
    _mod('GtApp', GtApp=lambda *a, **k: _App())
    fp = _mod('fermipy'); fp.__path__ = []
    _mod('fermipy.gtanalysis', GTAnalysis=object)

class _MinuitObj:
    def getQuality(self): return 3
    def getRetCode(self): return 0
