"""Fit parametric distributions and report goodness-of-fit for Task I."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from analysis.plot_common import FIGSIZE, save_figure, use_plot_style

DistributionSpec = Tuple[str, Callable[..., Tuple[float, ...]], int]

# (label, scipy rv, free-parameter count with floc=0 where applicable)
CANDIDATE_DISTRIBUTIONS: dict[str, DistributionSpec] = {
    "exponential": ("exponential", stats.expon.fit, 1),
    "lognormal": ("lognormal", stats.lognorm.fit, 2),
    "pareto": ("pareto", stats.pareto.fit, 2),
    "weibull": ("weibull", stats.weibull_min.fit, 2),
    "gamma": ("gamma", stats.gamma.fit, 2),
}

DEFAULT_CANDIDATES = ("exponential", "lognormal", "weibull", "gamma")


@dataclass(frozen=True)
class FitResult:
    dataset: str
    distribution: str
    n: int
    params: dict[str, float]
    ks_statistic: float
    ks_pvalue: float
    aic: float
    bic: float
    log_likelihood: float

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["params"] = dict(self.params)
        return row


def _param_names(dist_name: str, param_tuple: tuple[float, ...]) -> dict[str, float]:
    if dist_name == "exponential":
        loc, scale = param_tuple
        return {"loc": float(loc), "scale": float(scale)}
    shape, loc, scale = param_tuple
    return {"shape": float(shape), "loc": float(loc), "scale": float(scale)}


def _rv(dist_name: str):
    mapping = {
        "exponential": stats.expon,
        "poisson": stats.expon,
        "lognormal": stats.lognorm,
        "pareto": stats.pareto,
        "weibull": stats.weibull_min,
        "gamma": stats.gamma,
    }
    return mapping[dist_name]


def _fit_poisson_process_iat(values: np.ndarray, *, dataset: str) -> FitResult | None:
    """Poisson arrivals => exponential inter-arrival times (rate lambda = 1 / mean IAT)."""
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    data = data[data > 0]
    if len(data) < 10:
        return None

    try:
        params = stats.expon.fit(data, floc=0)
    except (FloatingPointError, ValueError, RuntimeError):
        return None

    mean_iat = float(np.mean(data))
    rate = 1.0 / mean_iat
    rv = stats.expon
    ks_stat, ks_p = stats.kstest(data, rv.cdf, args=params)
    ll = _log_likelihood(data, "exponential", params)
    n_params = 1
    aic = 2 * n_params - 2 * ll
    bic = n_params * np.log(len(data)) - 2 * ll

    return FitResult(
        dataset=dataset,
        distribution="poisson",
        n=len(data),
        params={"lambda": rate, "mean_iat": mean_iat, "scale": float(params[1])},
        ks_statistic=float(ks_stat),
        ks_pvalue=float(ks_p),
        aic=float(aic),
        bic=float(bic),
        log_likelihood=float(ll),
    )


def _log_likelihood(values: np.ndarray, dist_name: str, param_tuple: tuple[float, ...]) -> float:
    rv = _rv(dist_name)
    logpdf = rv.logpdf(values, *param_tuple)
    if not np.all(np.isfinite(logpdf)):
        return float("-inf")
    return float(np.sum(logpdf))


def fit_single(
    values: np.ndarray,
    *,
    dataset: str,
    dist_key: str,
) -> FitResult | None:
    if dist_key == "poisson":
        return _fit_poisson_process_iat(values, dataset=dataset)

    if dist_key not in CANDIDATE_DISTRIBUTIONS:
        raise ValueError(f"Unknown distribution: {dist_key}")

    dist_name, fitter, n_params = CANDIDATE_DISTRIBUTIONS[dist_key]
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    data = data[data > 0]
    if len(data) < 10:
        return None

    try:
        params = fitter(data, floc=0)
    except (FloatingPointError, ValueError, RuntimeError):
        return None

    rv = _rv(dist_name)
    ks_stat, ks_p = stats.kstest(data, rv.cdf, args=params)
    ll = _log_likelihood(data, dist_name, params)
    aic = 2 * n_params - 2 * ll
    bic = n_params * np.log(len(data)) - 2 * ll

    return FitResult(
        dataset=dataset,
        distribution=dist_name,
        n=len(data),
        params=_param_names(dist_name, params),
        ks_statistic=float(ks_stat),
        ks_pvalue=float(ks_p),
        aic=float(aic),
        bic=float(bic),
        log_likelihood=float(ll),
    )


def compare_candidates(
    values: np.ndarray,
    *,
    dataset: str,
    candidates: tuple[str, ...] = DEFAULT_CANDIDATES,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key in candidates:
        result = fit_single(values, dataset=dataset, dist_key=key)
        if result is None:
            continue
        row = result.to_dict()
        row["rank_aic"] = None
        row["rank_bic"] = None
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["rank_aic"] = df["aic"].rank(method="min").astype(int)
    df["rank_bic"] = df["bic"].rank(method="min").astype(int)
    df = df.sort_values(["aic", "bic"]).reset_index(drop=True)
    return df


def best_fit(values: np.ndarray, *, dataset: str, candidates: tuple[str, ...] = DEFAULT_CANDIDATES) -> FitResult | None:
    df = compare_candidates(values, dataset=dataset, candidates=candidates)
    if df.empty:
        return None
    top = df.iloc[0]
    return FitResult(
        dataset=str(top["dataset"]),
        distribution=str(top["distribution"]),
        n=int(top["n"]),
        params={k: float(v) for k, v in top["params"].items()},
        ks_statistic=float(top["ks_statistic"]),
        ks_pvalue=float(top["ks_pvalue"]),
        aic=float(top["aic"]),
        bic=float(top["bic"]),
        log_likelihood=float(top["log_likelihood"]),
    )


def _params_tuple(dist_name: str, params: dict[str, float]) -> tuple[float, ...]:
    if dist_name in ("exponential", "poisson"):
        if dist_name == "poisson" and "lambda" in params and params["lambda"] > 0:
            return (0.0, 1.0 / params["lambda"])
        return (params.get("loc", 0.0), params["scale"])
    return (params["shape"], params.get("loc", 0.0), params["scale"])


def plot_pdf_with_fit(
    values: np.ndarray,
    fit: FitResult,
    *,
    out_path,
    xlabel: str,
    title: str,
    log_x: bool = False,
    log_y: bool = False,
    bins: int = 80,
) -> None:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    data = data[data > 0]
    if len(data) == 0:
        return

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.hist(
        data,
        bins=bins if not log_x else np.logspace(np.log10(data.min()), np.log10(data.max()), bins + 1),
        density=True,
        alpha=0.65,
        color="#4C72B0",
        edgecolor="white",
        linewidth=0.4,
        label="empirical",
    )

    rv = _rv(fit.distribution)
    params = _params_tuple(fit.distribution, fit.params)
    if log_x:
        x = np.logspace(np.log10(data.min()), np.log10(data.max()), 400)
    else:
        x = np.linspace(data.min(), data.max(), 400)
    y = rv.pdf(x, *params)
    ax.plot(
        x,
        y,
        color="#E64B35",
        linewidth=2.0,
        label=f"{fit.distribution} (KS D={fit.ks_statistic:.3f}, p={fit.ks_pvalue:.1e})",
    )

    if log_x:
        ax.set_xscale("log")
    if log_y:
        ax.set_yscale("log")
        ymin, ymax = ax.get_ylim()
        if ymin <= 0:
            ax.set_ylim(bottom=max(ymax * 1e-6, 1e-12), top=ymax)

    ax.set_xlabel(xlabel)
    ax.set_ylabel("Density")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3, which="both" if (log_x or log_y) else "major")
    save_figure(fig, out_path)
    plt.style.use("default")


def plot_qq(
    values: np.ndarray,
    fit: FitResult,
    *,
    out_path,
    title: str,
) -> None:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    data = data[data > 0]
    if len(data) == 0:
        return

    rv = _rv(fit.distribution)
    params = _params_tuple(fit.distribution, fit.params)

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    stats.probplot(data, dist=rv, sparams=params, plot=ax)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    save_figure(fig, out_path)
    plt.style.use("default")


def fit_result_from_row(row: pd.Series | dict[str, Any], *, dataset: str | None = None) -> FitResult:
    if isinstance(row, pd.Series):
        data = row.to_dict()
    else:
        data = dict(row)
    params = data["params"]
    if not isinstance(params, dict):
        params = dict(params)
    return FitResult(
        dataset=str(dataset or data.get("dataset", "")),
        distribution=str(data["distribution"]),
        n=int(data["n"]),
        params={k: float(v) for k, v in params.items()},
        ks_statistic=float(data["ks_statistic"]),
        ks_pvalue=float(data["ks_pvalue"]),
        aic=float(data["aic"]),
        bic=float(data["bic"]),
        log_likelihood=float(data["log_likelihood"]),
    )


def fit_summary_caption(fit: FitResult) -> str:
    param_bits = ", ".join(f"{k}={v:.4g}" for k, v in fit.params.items())
    return (
        f"best={fit.distribution} ({param_bits}); "
        f"KS D={fit.ks_statistic:.4f}, p={fit.ks_pvalue:.2e}; "
        f"AIC={fit.aic:.1f}, BIC={fit.bic:.1f}"
    )
