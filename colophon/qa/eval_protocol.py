"""Eval-protocol fingerprinting.

A QA pass is only trustworthy if you can tie it to the *exact* gate code and
runtime that produced it. We hash the gate source plus the Python/runtime
versions into one fingerprint, so two runs are comparable only when their
fingerprints match. Change a gate, bump a dependency, and the fingerprint
changes -- which is the whole point: you can never silently compare results
across two different judges.

This is the "byte-identical / golden-file" discipline applied to the *judge
itself*: the evaluation protocol is versioned as a first-class artifact, so a
result is only ever comparable to another result produced by the same judge.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

#: Bump this when the *meaning* of a pass changes (new gate, new failure
#: semantics) even if no source bytes changed.
EVAL_PROTOCOL = "colophon-qa-v1"

_GATE_DIR = Path(__file__).resolve().parent / "stages"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _gate_code_fingerprint() -> str:
    """Stable SHA-256 over the gate source, namespaced by the protocol id."""
    files = sorted(_GATE_DIR.glob("*.py"))
    digest = hashlib.sha256()
    digest.update(EVAL_PROTOCOL.encode("utf-8"))
    digest.update(b"\0")
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _colophon_version() -> str:
    try:
        return importlib.metadata.version("colophon")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()[:12]
    except (subprocess.SubprocessError, OSError):
        pass
    return "unknown"


def _runtime_fingerprint() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "colophon": _colophon_version(),
        "git_sha": _git_sha(),
    }


def compute_eval_fingerprint() -> dict[str, Any]:
    """Return the judge fingerprint for the current gate set and runtime."""
    return {
        "protocol": EVAL_PROTOCOL,
        "gate_code": _gate_code_fingerprint(),
        "runtime": _runtime_fingerprint(),
    }


def format_eval_fingerprint(fp: dict[str, Any]) -> str:
    rt = fp["runtime"]
    return (
        f"eval {fp['protocol']}  gate={fp['gate_code']}  "
        f"py={rt['python']} colophon={rt['colophon']} git={rt['git_sha']}"
    )
