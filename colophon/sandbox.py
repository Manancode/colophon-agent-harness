"""Keeping a server's filesystem access inside the directory it was given.

Colophon's tool functions take a path from their caller and write where the
caller says. As a library that is the right behaviour: the caller *is* the
process, and a library that refused to write outside one directory would be a
library nobody could use.

As a server it is a confused deputy. The client naming the path is not the
user running the process, so a client that can name ``/etc`` — or a second
project's source tree — gets the server to overwrite files on its behalf using
the server's privileges. Colophon makes this worse rather than better: the
writing tools carry no annotation, precisely so an agent is not interrupted by
an approval prompt mid-loop, so there is no prompt to notice the write.

So the server gets a root, and every path a tool is handed must resolve inside
it. Nothing is guarded until :func:`configure` is called, which
``colophon mcp serve`` does on startup; the CLI and the library stay
unconstrained on purpose, since neither has a deputy to confuse.

Symlinks are resolved *before* the check, so a link that sits inside the root
but points outside is refused rather than followed.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Environment variable naming the root, for deployments that would rather
#: not pass a flag. The command-line flag wins when both are present.
ROOT_ENV = "COLOPHON_ROOT"

_root: Path | None = None


class PathEscapeError(Exception):
    """A caller-supplied path resolves outside the server's root."""


def configure(root: str | Path | None = None) -> Path:
    """Set the root every tool path will be confined to, and return it.

    With no root given, this falls back to :envvar:`COLOPHON_ROOT` and then to
    the directory the server was started in. That default is deliberate: it
    makes the blast radius the operator's own choice of working directory
    rather than the entire filesystem, and it needs no configuration to be
    safe.
    """
    global _root
    chosen = root if root is not None else os.environ.get(ROOT_ENV) or os.getcwd()
    _root = Path(chosen).expanduser().resolve()
    return _root


def reset() -> None:
    """Remove the root. This is the library default, and what tests need."""
    global _root
    _root = None


def root() -> Path | None:
    """The configured root, or ``None`` when the library is being used directly."""
    return _root


def within(path: str | Path, *, label: str = "path") -> Path:
    """Resolve ``path`` and require it to sit inside the configured root.

    Returns the resolved path when no root is configured, which is the library
    case: no root means no deputy, so there is nothing to confine.
    """
    resolved = Path(path).expanduser().resolve()
    if _root is None:
        return resolved
    if resolved != _root and not resolved.is_relative_to(_root):
        raise PathEscapeError(
            f"{label} {resolved} is outside the server root {_root}; refusing "
            f"to touch it. Start the server with a --root that covers the "
            f"paths it needs, or set {ROOT_ENV}."
        )
    return resolved


def within_optional(path: str | Path | None, *, label: str = "path") -> Path | None:
    """``within`` for a path a tool is allowed to be given as ``None``."""
    return None if path is None else within(path, label=label)
