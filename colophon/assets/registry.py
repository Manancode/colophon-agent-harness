"""Asset resolution. Local only, content addressed.

No remote asset may enter a render. A video that references
``https://cdn.example.com/logo.png`` is not reproducible — the URL can change,
expire, or start serving something else, and the render would change without
the spec changing. Everything is resolved from the example/run directory and
verified against its recorded sha256.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..spec.hash import sha256_file
from ..spec.schema import Asset, VideoSpec

_REMOTE = ("http://", "https://", "//", "ftp://", "data:")


class AssetError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedAsset:
    asset_id: str
    kind: str
    abs_path: Path
    rel_path: str
    sha256: str
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "kind": self.kind,
            "rel_path": self.rel_path,
            "sha256": self.sha256,
            "verified": self.verified,
        }


class AssetRegistry:
    """Resolves spec asset references against a base directory."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()

    def resolve(self, asset: Asset, *, verify: bool = True) -> ResolvedAsset:
        if any(asset.path.startswith(p) for p in _REMOTE):
            raise AssetError(f"asset {asset.asset_id}: remote paths are not permitted")

        candidate = Path(asset.path)
        if not candidate.is_absolute():
            candidate = self.base_dir / candidate

        # keep every asset inside the project root
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self.base_dir)
        except ValueError as exc:
            raise AssetError(
                f"asset {asset.asset_id}: {asset.path} escapes the project root "
                f"{self.base_dir}"
            ) from exc

        if not resolved.exists():
            raise AssetError(f"asset {asset.asset_id}: missing file {resolved}")

        actual = sha256_file(str(resolved)) if verify else ""
        verified = False
        if asset.sha256:
            if actual != asset.sha256:
                raise AssetError(
                    f"asset {asset.asset_id}: sha256 mismatch — spec says "
                    f"{asset.sha256[:12]}…, file is {actual[:12]}…"
                )
            verified = True

        return ResolvedAsset(
            asset_id=asset.asset_id,
            kind=asset.kind,
            abs_path=resolved,
            rel_path=str(resolved.relative_to(self.base_dir)),
            sha256=actual or asset.sha256,
            verified=verified,
        )

    def resolve_spec(self, spec: VideoSpec, *, verify: bool = True) -> dict[str, ResolvedAsset]:
        out: dict[str, ResolvedAsset] = {}
        for asset in spec.assets:
            out[asset.asset_id] = self.resolve(asset, verify=verify)
        return out


def hash_assets(base_dir: str | Path, assets: list[Asset]) -> list[Asset]:
    """Return copies of ``assets`` with sha256 filled in from disk."""
    registry = AssetRegistry(base_dir)
    from dataclasses import replace

    out: list[Asset] = []
    for asset in assets:
        resolved = registry.resolve(asset, verify=False)
        out.append(replace(asset, sha256=resolved.sha256))
    return out
