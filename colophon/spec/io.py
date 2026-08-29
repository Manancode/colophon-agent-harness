"""Deterministic spec (de)serialisation.

Canonical JSON is the backbone of reproducibility: the same spec object must
always produce byte-identical output, so its hash is stable across machines,
Python versions and runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import VideoSpec

_ENSURE_ASCII = False
_INDENT = 2


def canonical_bytes(obj: Any) -> bytes:
    """Serialise to stable bytes. Keys sorted, no ASCII escaping, UTF-8."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=_ENSURE_ASCII,
    ).encode("utf-8")


def canonical_pretty(obj: Any) -> str:
    """Human-readable form of the same bytes (indentation only)."""
    return json.dumps(obj, sort_keys=True, indent=_INDENT, ensure_ascii=_ENSURE_ASCII)


def dumps(spec: VideoSpec, *, pretty: bool = True) -> str:
    obj = spec.to_dict()
    return canonical_pretty(obj) if pretty else canonical_bytes(obj).decode("utf-8")


def load(path: str | Path) -> VideoSpec:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: spec must be a JSON object")
    from .schema import VideoSpec as _VS  # local import keeps cycle surface small

    return _VS.from_dict(raw)


def save(spec: VideoSpec, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(spec) + "\n", encoding="utf-8")
    return path


def write_json(obj: Any, path: str | Path) -> Path:
    """Write an arbitrary dict with the same canonical rules."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_pretty(obj) + "\n", encoding="utf-8")
    return path
