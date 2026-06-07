"""Time-series distribution plots (reserved for future PDF/CCDF work)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def plot_all(
    packets: pd.DataFrame,
    *,
    results_root: str | Path | None = None,
) -> list[Path]:
    del packets, results_root
    return []
