"""Executable discovery and pinning.

Colophon shells out to node, ffmpeg and ffprobe. Two lessons are baked in
here, both learned the hard way:

1. **Resolve, then hash the resolved paths.** If the runtime cache key is
   derived from resolved binary paths, the same tools reached through a
   different PATH produce a *different* cache key and the run declares its
   own cache "absent". The sandbox PATH omits ``/opt/homebrew``, which is how
   we hit that. We record what we actually resolved so the mismatch is
   explainable instead of mysterious.

2. **Pin by version, not by hope.** A renderer pinned to 0.7.86 that silently
   resolves to 0.7.90 is not a reproducible run.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Tool:
    name: str
    path: Path | None = None
    version: str = ""
    found: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path) if self.path else None,
            "version": self.version,
            "found": self.found,
        }


class ToolError(RuntimeError):
    pass


#: Directories that are commonly present in a login shell but missing from a
#: sandboxed one. Prepending these is the difference between "ffmpeg not
#: found" and a working run.
EXTRA_PATH_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/opt/local/bin",
)


def effective_path() -> str:
    parts = [os.environ.get("PATH") or ""]
    for d in EXTRA_PATH_DIRS:
        if Path(d).is_dir() and d not in parts[0]:
            parts.append(d)
    return os.pathsep.join(p for p in parts if p)


def _which(name: str) -> Path | None:
    found = shutil.which(name, path=effective_path())
    if not found:
        return None
    try:
        return Path(found).resolve()
    except OSError:
        return Path(found)


def _version(binary: Path, flag: str = "--version") -> str:
    try:
        proc = subprocess.run(
            [str(binary), flag],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    blob = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", blob)
    return m.group(1) if m else ""


def resolve(name: str, *, version_flag: str = "--version", required: bool = True) -> Tool:
    path = _which(name)
    if path is None:
        if required:
            raise ToolError(
                f"{name} not found on PATH (searched: {effective_path()})"
            )
        return Tool(name=name)
    return Tool(name=name, path=path, version=_version(path, version_flag), found=True)


def resolve_runtime() -> dict[str, Tool]:
    """Resolve everything a HyperFrames run needs."""
    return {
        "node": resolve("node"),
        "npm": resolve("npm"),
        "ffmpeg": resolve("ffmpeg"),
        "ffprobe": resolve("ffprobe"),
    }


def cache_key(tools: dict[str, Tool], *, extra: str = "") -> str:
    """Stable key from the *resolved* paths, not the names."""
    payload = "|".join(
        f"{k}={tools[k].path}:{tools[k].version}" for k in sorted(tools)
    )
    if extra:
        payload += f"|{extra}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def run(
    argv: list[str],
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
) -> tuple[int, str, str]:
    """Run a command with the effective PATH. Returns (code, stdout, stderr)."""
    merged = dict(os.environ)
    merged["PATH"] = effective_path()
    if env:
        merged.update(env)
    proc = subprocess.run(
        [str(a) for a in argv],
        cwd=str(cwd) if cwd else None,
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""
