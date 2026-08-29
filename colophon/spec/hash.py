"""Spec fingerprints and per-scene locality hashes.

Two hashes are used throughout a run:

``spec_sha256``
    Hash of the whole canonical spec. Every artifact produced by a run records
    it, so an artifact can always be traced back to the exact spec that made it.

``scene_sha256``
    Hash of one scene plus the canvas and claims it references. Repair uses
    these to prove *locality*: after a targeted edit, only the edited scenes'
    hashes should change. If unrelated scenes move, the edit was not local and
    the re-render cannot be trusted as a partial repair.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from .io import canonical_bytes
from .schema import VideoSpec


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_bytes(canonical_bytes(obj))


def spec_sha256(spec: VideoSpec) -> str:
    return sha256_obj(spec.to_dict())


def scene_payload(spec: VideoSpec, scene_id: str) -> dict[str, Any]:
    """The minimal object that fully determines one scene's rendering."""
    scene = next((s for s in spec.scenes if s.scene_id == scene_id), None)
    if scene is None:
        raise KeyError(scene_id)

    claims = {}
    for cid in (scene.title_claim_id, scene.narration_claim_id):
        if cid is None:
            continue
        claim = spec.claim(cid)
        if claim is not None:
            claims[cid] = claim.to_dict()

    assets = {}
    for aid in scene.asset_ids:
        asset = spec.asset(aid)
        if asset is not None:
            assets[aid] = asset.to_dict()

    return {
        "spec_version": spec.spec_version,
        "canvas": spec.canvas.to_dict(),
        "brand": spec.brand.to_dict() if spec.brand else None,
        "scene": scene.to_dict(),
        "claims": claims,
        "assets": assets,
    }


def scene_sha256(spec: VideoSpec, scene_id: str) -> str:
    return sha256_obj(scene_payload(spec, scene_id))


def scene_hashes(spec: VideoSpec) -> dict[str, str]:
    return {s.scene_id: scene_sha256(spec, s.scene_id) for s in spec.scenes}


def diff_scene_hashes(
    before: Mapping[str, str], after: Mapping[str, str]
) -> dict[str, list[str]]:
    """Compare two scene-hash maps. Returns added / removed / changed."""
    keys_before, keys_after = set(before), set(after)
    return {
        "added": sorted(keys_after - keys_before),
        "removed": sorted(keys_before - keys_after),
        "changed": sorted(k for k in keys_before & keys_after if before[k] != after[k]),
        "unchanged": sorted(k for k in keys_before & keys_after if before[k] == after[k]),
    }
