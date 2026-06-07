"""Resolve task2 vs monorepo paths (Docker /p4 + /repo mount vs local checkout)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

_TASK2_ROOT = Path(__file__).resolve().parents[1]


def task2_root() -> Path:
    """Directory containing p4src/, control_plane/, Makefile ( /p4 in Docker )."""
    return _TASK2_ROOT


def repo_root() -> Path:
    """Repository root containing task1/ and task2/."""
    docker_repo = Path("/repo")
    if (docker_repo / "task1" / "src" / "analysis").is_dir():
        return docker_repo
    candidate = _TASK2_ROOT.parent
    if (candidate / "task1" / "src" / "analysis").is_dir():
        return candidate
    raise FileNotFoundError(
        "Cannot find task1/src/analysis. "
        "In Docker, mount the repo at /repo (see docker-compose.yml). "
        f"Checked /repo and {candidate}."
    )


def task1_src() -> Path:
    return repo_root() / "task1" / "src"


def _ensure_analysis_package_stub(src: Path) -> None:
    """Register a lightweight analysis package without running analysis/__init__.py."""
    name = "analysis"
    if name in sys.modules:
        return
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(src / name)]  # type: ignore[attr-defined]
    pkg.__package__ = name
    sys.modules[name] = pkg


def ensure_task1_on_path() -> Path:
    src = task1_src()
    text = str(src)
    if text not in sys.path:
        sys.path.insert(0, text)
    _ensure_analysis_package_stub(src)
    return src
