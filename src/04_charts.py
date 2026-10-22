"""Build the three portfolio charts from the saved outputs."""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
FIG = OUT / "charts"
FIG.mkdir(exist_ok=True)

BLUE, ORANGE, GREEN, RED, GREY = "#2a6fdb", "#e08a1e", "#2e9e6b", "#d1495b", "#8a8f98"
plt.rcParams.update({
    "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "figure.dpi": 130,
})

el = pd.read_csv(OUT / "elasticity_by_product.csv", dtype={"stock_code": str})
seg = pd.read_csv(OUT / "segments.csv", dtype={"stock_code": str})
depth = pd.read_csv(OUT / "promo_by_depth.csv")


def chart_elasticity():
    fig, ax = plt.subplots(figsize=(8, 4.6))
    bins = np.linspace(-8, 2, 51)
    for method, color, label in (("naive", ORANGE, "Naive (revenue ÷ qty, all orders)"),
                                 ("robust", BLUE, "Robust (list price, small orders)")):
        v = el[(el["method"] == method) & el["significant"]]["elasticity"].clip(-8, 2)
        ax.hist(v, bins=bins, alpha=0.6, color=color, label=label)
        med = v.median()
        ax.axvline(med, color=color, lw=2, ls="--")
        ax.text(med, ax.get_ylim()[1] * (0.92 if method == "robust" else 0.82), f" median {med:.2f}",
                color=color, fontweight="bold", ha="left" if method == "robust" else "right")
    ax.set_xlabel("Price elasticity of demand (values beyond -8 / +2 clipped)")
    ax.set_ylabel("Products (significant, p<0.05)")
    ax.set_title("Bulk discounts overstated price sensitivity by about a quarter")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "1_elasticity_naive_vs_robust.png")
    plt.close(fig)


def chart_promos():
    order = ["shallow (15-30%)", "medium (30-40%)", "deep clearance (>40%)"]
    d = depth.set_index("depth").loc[order]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    colors = [GREEN if v > 0 else RED for v in d["net_profit_assumed_cost"]]
    axes[0].bar(range(3), d["net_profit_assumed_cost"] / 1000, color=colors)
    axes[0].axhline(0, color="black", lw=0.8)
    axes[0].set_xticks(range(3), [o.replace(" (", "\n(") for o in order])
    axes[0].set_ylabel("Net incremental profit, $K (assumed 60% cost)")
    axes[0].set_title("Only shallow promos made money")
    axes[0].set_ylim(-150, 45)
    for i, v in enumerate(d["net_profit_assumed_cost"] / 1000):
        axes[0].text(i, v + (4 if v > 0 else -4), f"{v:+.0f}K", ha="center",
                     va="bottom" if v > 0 else "top", fontweight="bold")

    w = 0.38
    x = np.arange(3)
    axes[1].bar(x - w / 2, d["pct_revenue_positive"], w, color=BLUE, label="Revenue-positive")
    axes[1].bar(x + w / 2, d["pct_profit_positive"], w, color=ORANGE, label="Profit-positive")
    axes[1].set_xticks(x, [o.replace(" (", "\n(") for o in order])
    axes[1].set_ylabel("% of promoted products")
    axes[1].set_ylim(0, 115)
    axes[1].set_title("Deep clearance sells but rarely pays")
    axes[1].legend(frameon=False, loc="upper center", ncol=2)
    for i, (r, p) in enumerate(zip(d["pct_revenue_positive"], d["pct_profit_positive"])):
        axes[1].text(i - w / 2, r + 1.5, f"{r:.0f}%", ha="center", fontsize=9)
        axes[1].text(i + w / 2, p + 1.5, f"{p:.0f}%", ha="center", fontsize=9)
    fig.suptitle("Promo results by discount depth (731 products)", fontweight="bold", y=1.0)
    fig.tight_layout()
    fig.savefig(FIG / "2_promo_by_depth.png", bbox_inches="tight")
    plt.close(fig)


def chart_segments():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    ss = seg.groupby("segment").agg(n=("stock_code", "count"), impact=("annual_profit_impact", "sum"))
    ss = ss.loc[["Raise price", "Hold", "Discount"]]
    cols = [GREEN, GREY, BLUE]
    axes[0].bar(ss.index, ss["impact"] / 1000, color=cols)
    axes[0].set_ylabel("Est. annual profit impact of a ±5% move, $K")
    axes[0].set_title("Raising prices is where the upside is")
    for i, (n, v) in enumerate(zip(ss["n"], ss["impact"] / 1000)):
        axes[0].text(i, v + 1, f"+${v:.0f}K\n{n:,} products" if v else f"$0\n{n:,} products", ha="center", fontsize=10)
    axes[0].set_ylim(0, ss["impact"].max() / 1000 * 1.3)

    rows = []
    for cr in (0.5, 0.6, 0.7):
        th = 1 / (1 - cr)
        a = seg["elasticity_robust"].abs()
        rows.append((cr, (seg["reliable"] & (a < th)).sum(),
                     (seg["reliable"] & (a > th) & (seg["net_incremental_profit"].fillna(-1) > 0)).sum()))
    sens = pd.DataFrame(rows, columns=["cost", "raise", "discount"])
    x = np.arange(3)
    axes[1].bar(x - 0.2, sens["raise"], 0.4, color=GREEN, label="Raise price")
    axes[1].bar(x + 0.2, sens["discount"], 0.4, color=BLUE, label="Discount")
    axes[1].set_xticks(x, [f"{int(c * 100)}%" for c in sens["cost"]])
    axes[1].set_xlabel("Assumed unit cost as % of price")
    axes[1].set_ylabel("Products in segment")
    axes[1].set_title("Segment sizes depend on the cost assumption")
    axes[1].legend(frameon=False)
    for i, (r, d) in enumerate(zip(sens["raise"], sens["discount"])):
        axes[1].text(i - 0.2, r + 20, f"{r:,}", ha="center", fontsize=9)
        axes[1].text(i + 0.2, d + 20, f"{d:,}", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "3_segments.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    chart_elasticity()
    chart_promos()
    chart_segments()
    print("charts:", sorted(p.name for p in FIG.glob("*.png")))
