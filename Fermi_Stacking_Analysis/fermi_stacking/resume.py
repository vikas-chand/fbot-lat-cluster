"""Checkpoint/resume support for the stacking campaign.

WHY THIS EXISTS
---------------
Both run_preprocessing and run_stacking begin by shutil.rmtree()-ing their own
output directory, so an interrupted task did not merely fail to resume -- it
destroyed the work it had already done. A 16 h SLURM walltime killed a task two
thirds of the way through its last component and left nothing to salvage.

WHAT MAKES THIS SAFE
--------------------
Per-index-row resume is only sound because each row is independent: every fit is
re-initialised from the on-disk fit_model_3_0X.xml with all parameters frozen and
then explicitly set, the accumulators are rebuilt per row, and no RNG is
involved. Rows carry nothing forward.

But "independent given identical inputs" is the whole game, and the directory
name (event, window) does not encode the inputs. A preserved row from a run with
a different flux grid, energy ceiling, edisp setting or background model is
indistinguishable from a current one -- and in the flux-grid case the array shape
does not even change, so nothing downstream would notice. Hence scan_key(): the
resume is keyed on a hash of the configuration that actually determines the
numbers, and a mismatch discards the directory rather than resuming into it.

Completeness is likewise decided by content, never by existence. The row write is
truncating and non-atomic, so a kill mid-write leaves a short file; truncation at
a line boundary is caught loudly downstream, but truncation mid-line is parsed
silently into bad numbers. Rows are therefore written to a temp file, fsync'd and
renamed, and validated field-by-field on read -- including the index column,
which each row stamps on every line and which proves the file belongs to the row
it is named for.
"""
import hashlib
import json
import math
import os

RESUME_ENV = 'FS_RESUME'


def enabled():
    """Resume is on unless FS_RESUME=0. Turn it off to force a clean rerun."""
    return os.environ.get(RESUME_ENV, '1') != '0'


# --------------------------------------------------------------------------
# configuration identity
# --------------------------------------------------------------------------

def scan_key(inst, psf, extra=None):
    """Hash of everything that determines the numbers in a scan row.

    Deliberately includes the fitted background model and the source maps by
    content, not by path: re-running preprocessing produces a different ROI
    model, and rows computed against the old one must not be mixed with rows
    computed against the new one inside a single saved TS array.
    """
    parts = {
        'index_min': float(inst.index_min),
        'index_max': float(inst.index_max),
        'flux_min': float(inst.flux_min),
        'flux_max': float(inst.flux_max),
        'num_flux_bins': int(inst.num_flux_bins),
        'psf': int(psf),
        'irfs': str(getattr(inst, 'irfs', '')),
        'ltcube': _file_digest(getattr(inst, 'ltcube', '') or ''),
        # the analysis switches that run_task exports per task
        'env': {k: os.environ.get(k, '') for k in
                ('FS_EDISP', 'FS_FREE_RADIUS_DEG', 'FS_CATALOG_4FGL')},
    }
    if extra:
        parts.update(extra)
    blob = json.dumps(parts, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def _file_digest(path, limit=None):
    """sha256 of a file, or '' when absent. `limit` caps bytes read."""
    if not path or not os.path.isfile(path):
        return ''
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            if limit is not None and f.tell() >= limit:
                break
    return h.hexdigest()


def key_file(dirpath):
    return os.path.join(dirpath, '.scan_key.json')


def read_key(dirpath):
    try:
        with open(key_file(dirpath)) as f:
            return json.load(f).get('scan_key')
    except Exception:
        return None


def write_key(dirpath, key, note=None):
    payload = {'scan_key': key}
    if note:
        payload.update(note)
    tmp = key_file(dirpath) + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, key_file(dirpath))


# --------------------------------------------------------------------------
# per-row files
# --------------------------------------------------------------------------

def row_name(base_name, index_value):
    """The row filename, built exactly as run_stacking writes it."""
    return '%s_stacking_%s.txt' % (base_name, index_value)


def row_status(path, num_flux_bins, index_value):
    """Why a row file is or is not usable: one of

      ok | missing | empty | short | malformed | wrong_index | nonfinite

    Checks are cheapest-first. `nonfinite` is reported separately because it is
    NOT a truncation: a diverging Minuit fit writes 'nan', float('nan') parses
    happily, and the row would otherwise look complete and be summed straight
    into the stacked TS surface.
    """
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return 'missing'
    if not text.strip():
        return 'empty'
    lines = text.strip('\n').split('\n')
    if len(lines) != int(num_flux_bins):
        return 'short'
    want_index = '%.1f' % float(index_value)
    for line in lines:
        fields = line.split()
        if len(fields) != 5:
            return 'malformed'
        if fields[1] != want_index:
            return 'wrong_index'
        try:
            flux = float(fields[0]); like = float(fields[2])
            int(fields[3]); int(fields[4])
        except ValueError:
            return 'malformed'
        if not (math.isfinite(flux) and math.isfinite(like)):
            return 'nonfinite'
    return 'ok'


def row_is_complete(path, num_flux_bins, index_value):
    """True only if the row is complete, correctly labelled, and finite."""
    return row_status(path, num_flux_bins, index_value) == 'ok'


def write_row_atomic(path, text):
    """Write a row so that it is either absent or complete, never half-written."""
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# preprocessing completeness (all-or-nothing)
# --------------------------------------------------------------------------

def preprocessing_complete(src_output_main, ncomp):
    """Is a preprocessing directory complete and usable for all `ncomp` parts?

    All-or-nothing on purpose. fermipy skips regeneration on os.path.isfile
    alone with no integrity checking, and the source-finding stage mutates
    srcmaps in place, so a half-finished directory is not a clean function of
    the configuration. Anything short of complete means rmtree and redo.
    """
    out = os.path.join(src_output_main, 'output')
    if not os.path.isdir(out):
        return False
    if not _fits_ok(os.path.join(out, 'ltcube_00.fits')):
        return False
    for j in range(int(ncomp)):
        for name in ('srcmap_0%d.fits' % j, 'bexpmap_0%d.fits' % j):
            if not _fits_ok(os.path.join(out, name)):
                return False
        if not os.path.isfile(os.path.join(out, 'fit_model_3_0%d.xml' % j)):
            return False
        # the last artifact written per component, and opened 'w' before its
        # content is computed -- a kill leaves it 0 bytes, so parse it
        try:
            with open(os.path.join(out, 'null_likelihood_%d.txt' % j)) as f:
                float(f.readline().strip())
        except (OSError, ValueError):
            return False
    # a stale extra component would be silently summed in later
    if os.path.isfile(os.path.join(out, 'srcmap_0%d.fits' % int(ncomp))):
        return False
    return True


def _fits_ok(path):
    """Present, non-empty, and a whole number of FITS blocks."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    return size > 0 and size % 2880 == 0


def component_dirs(stacking_output):
    """`Likelihood_<int>` DIRECTORIES only, as (j, path), sorted by j.

    The original glob had no isdir filter and int()-parsed the suffix, so any
    stray file named Likelihood_something crashed it and any stale component
    directory silently added itself to the sum.
    """
    found = []
    if not os.path.isdir(stacking_output):
        return found
    for entry in sorted(os.listdir(stacking_output)):
        path = os.path.join(stacking_output, entry)
        if not os.path.isdir(path) or not entry.startswith('Likelihood_'):
            continue
        suffix = entry[len('Likelihood_'):]
        if not suffix.isdigit():
            continue
        found.append((int(suffix), path))
    return sorted(found)
