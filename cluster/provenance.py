#!/usr/bin/env python3
"""
What actually ran — measured, not declared.

The campaign previously stamped a hardcoded `fork_commit='24c84ee'` into every
task_meta.json and STACK_*.json, and ingest_cluster_results.py then checked that
string against its own copy of the same literal. The check therefore compared a
constant with itself: it passed no matter what code produced the products, and
after the portability fix (854d7b0) the string it certified was simply wrong.

Independent verification has to differ at the PRIMITIVE, not just at the agent.
So we fingerprint the pipeline source that the interpreter actually imported and
compare it, on return, against the same fingerprint computed from our own copy.
A stale package, an upstream install, or a local edit changes the hash and the
gate fires; nothing can agree with itself into a false pass.

Note `fermi_stacking` is vendored inside the campaign repo, so a `git rev-parse`
in its directory reports the CAMPAIGN repo's HEAD, not the fork's — which is why
the content hash, not a commit id, is the load-bearing quantity here.
"""
import hashlib
import subprocess
from pathlib import Path


def _package_dir():
    """The pipeline whose provenance we are recording.

    The imported package wins: on a worker, run_task.py has already put the
    configured copy on sys.path, and what ran is what must be stamped. Producers
    that never import it (collect_stack.py only reads .npy) fall back to the copy
    vendored beside this file.
    """
    try:
        import fermi_stacking
        return Path(fermi_stacking.__file__).resolve().parent
    except Exception:
        vendored = (Path(__file__).resolve().parent.parent
                    / 'Fermi_Stacking_Analysis' / 'fermi_stacking')
        if vendored.is_dir():
            return vendored
        raise


def pipeline_sha256(pkg=None):
    """SHA-256 over every .py in a fermi_stacking package.

    Defaults to the package this interpreter imported. Path-relative and sorted,
    so it is identical across machines and checkouts and changes if any line of
    the pipeline changes. `pkg` lets the home-side ingest hash OUR copy for the
    measured-vs-measured comparison.
    """
    pkg = Path(pkg) if pkg else _package_dir()
    h = hashlib.sha256()
    for p in sorted(pkg.rglob('*.py')):
        if '__pycache__' in p.parts:
            continue
        h.update(p.relative_to(pkg).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def repo_commit():
    """HEAD of the repository the pipeline is vendored in ('unknown' if absent)."""
    try:
        out = subprocess.run(
            ['git', '-C', str(_package_dir()), 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def fingerprint():
    """The provenance block embedded in every product.

    Never raises: a product that cannot prove what made it is stamped
    'unavailable', which fails the ingest gate rather than crashing a task that
    has already spent ten hours computing.
    """
    try:
        return {'pipeline_sha256': pipeline_sha256(),
                'repo_commit': repo_commit(),
                'pipeline_path': str(_package_dir())}
    except Exception as exc:
        return {'pipeline_sha256': 'unavailable',
                'repo_commit': 'unknown',
                'pipeline_path': f'unavailable: {exc}'}


if __name__ == '__main__':
    import json
    print(json.dumps(fingerprint(), indent=2))
