"""Promo analysis + raise / hold / discount segmentation.

Promo definition (no promo flag exists in the data):
  promo week  = weekly list price <= (1 - PROMO_DISCOUNT) * product's median weekly list price
  post window = the POST_WEEKS non-promo weeks after a promo week (looks for pulled-forward demand)
  baseline    = all other weeks
Quantities are seasonally adjusted with a month index built from total retail-size demand.
Zero-sale weeks inside a product's life are kept as 0 (otherwise averages are biased upward).

Segmentation uses the robust elasticity and an ASSUMED unit cost = COST_RATIO * price:
  price up is profitable  iff |e| < 1 / margin   (margin = 1 - COST_RATIO)
  price down is profitable iff |e| > 1 / margin
"""
import importlib.util
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "retail.db"
OUT = ROOT / "outputs"

PROMO_DISCOUNT = 0.15
POST_WEEKS = 4
MIN_PROMO_WEEKS = 3
MIN_BASE_WEEKS = 10
COST_RATIO = 0.60  # ASSUMPTION: dataset has no cost data
PRICE_STEP = 0.05  # size of the price move used to size impact

spec = importlib.util.spec_from_file_location("elast", ROOT / "src" / "02_elasticity.py")
elast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(elast)


def promo_analysis(df):
    w = elast.weekly_robust(df)
    w["week"] = pd.to_datetime(w["week"])
    w["month"] = w["week"].dt.month

    # month seasonality index from total retail-size demand
    tot = w.groupby("week").agg(q=("qty", "sum")).reset_index()
    tot["month"] = tot["week"].dt.month
    idx = tot.groupby("month")["q"].mean()
    idx = idx / idx.mean()

    rows = []
    for code, g in w.groupby("stock_code"):
        g = g.set_index("week").sort_index()
        if len(g) < elast.MIN_WEEKS:
            continue
        full = pd.date_range(g.index.min(), g.index.max(), freq="W-MON")
        g = g.reindex(full)
        g["qty"] = g["qty"].fillna(0)
        g["month"] = g.index.month
        g["qty_adj"] = g["qty"] / g["month"].map(idx)
        ref = g["price"].median()
        g["promo"] = g["price"] <= (1 - PROMO_DISCOUNT) * ref
        # post window: non-promo weeks within POST_WEEKS after a promo week
        recent = g["promo"].astype(int).rolling(POST_WEEKS + 1, min_periods=1).max().shift(1).fillna(0).astype(bool)
        g["post"] = recent & ~g["promo"]
        g["base"] = ~g["promo"] & ~g["post"]
        if g["promo"].sum() < MIN_PROMO_WEEKS or g["base"].sum() < MIN_BASE_WEEKS:
            continue
        b = g.loc[g["base"], "qty_adj"].mean()
        if b <= 0:
            continue
        p_mean = g.loc[g["promo"], "qty_adj"].mean()
        post_mean = g.loc[g["post"], "qty_adj"].mean() if g["post"].any() else b
        n_p, n_post = int(g["promo"].sum()), int(g["post"].sum())
        promo_price = g.loc[g["promo"], "price"].mean()
        base_price = g.loc[g["base"], "price"].median()
        inc_units = (p_mean - b) * n_p + (post_mean - b) * n_post
        inc_rev = (p_mean * promo_price - b * base_price) * n_p + (post_mean - b) * base_price * n_post
        inc_profit = (p_mean * (promo_price - COST_RATIO * base_price) - b * (base_price - COST_RATIO * base_price)) * n_p \
            + (post_mean - b) * (base_price - COST_RATIO * base_price) * n_post
        rows.append(dict(
            stock_code=code, description=g["description"].dropna().iloc[0], promo_weeks=n_p, post_weeks=n_post,
            base_weeks=int(g["base"].sum()), base_price=base_price, promo_price=promo_price,
            avg_discount=1 - promo_price / base_price, base_qty=b, promo_qty=p_mean, post_qty=post_mean,
            promo_lift=p_mean / b - 1, post_dip=post_mean / b - 1,
            net_incremental_units=inc_units, net_incremental_revenue=inc_rev, net_incremental_profit=inc_profit,
        ))
    return pd.DataFrame(rows)


def segment(df_el, promos):
    r = df_el[df_el["method"] == "robust"].set_index("stock_code")
    n = df_el[df_el["method"] == "naive"].set_index("stock_code")
    s = r.join(n[["elasticity"]].rename(columns={"elasticity": "elasticity_naive"}), how="inner").reset_index()
    s = s.rename(columns={"elasticity": "elasticity_robust"})
    s = s.merge(promos[["stock_code", "net_incremental_profit", "promo_lift", "post_dip"]], on="stock_code", how="left")

    margin = 1 - COST_RATIO
    thresh = 1 / margin  # |e| break-even
    abs_e = s["elasticity_robust"].abs()
    # reliable = robust significant, both methods agree on a negative sign
    reliable = s["significant"] & (s["elasticity_robust"] < 0) & (s["elasticity_naive"] < 0)
    confident_up = (abs_e + 1.96 * s["std_err"]) < thresh

    s["segment"] = "Hold"
    s.loc[reliable & (abs_e < thresh), "segment"] = "Raise price"
    s.loc[reliable & (abs_e > thresh) & (s["net_incremental_profit"].fillna(-1) > 0), "segment"] = "Discount"
    s["reliable"] = reliable
    s["confident"] = np.where(s["segment"] == "Raise price", confident_up, np.nan)

    # annual retail-size profit impact of a +/-PRICE_STEP move
    s["annual_qty"] = s["total_qty"] / s["weeks"] * 52
    P, e, Q = s["mean_price"], s["elasticity_robust"], s["annual_qty"]
    c = COST_RATIO * P
    base_profit = Q * (P - c)
    delta = np.where(s["segment"] == "Raise price", PRICE_STEP, np.where(s["segment"] == "Discount", -PRICE_STEP, 0.0))
    new_profit = Q * (1 + delta) ** e * (P * (1 + delta) - c)
    s["annual_profit_impact"] = new_profit - base_profit
    return s


def main():
    with sqlite3.connect(DB) as con:
        df = pd.read_sql("SELECT stock_code, description, week, quantity, unit_price, revenue FROM transactions", con)

    promos = promo_analysis(df)
    promos.to_csv(OUT / "promo_by_product.csv", index=False)

    summ = pd.Series({
        "products_with_promos": len(promos),
        "median_discount_pct": round(100 * promos["avg_discount"].median(), 1),
        "median_promo_lift_pct": round(100 * promos["promo_lift"].median(), 1),
        "median_post_dip_pct": round(100 * promos["post_dip"].median(), 1),
        "pct_promos_net_profitable": round(100 * (promos["net_incremental_profit"] > 0).mean(), 1),
        "pct_promos_net_revenue_positive": round(100 * (promos["net_incremental_revenue"] > 0).mean(), 1),
        "total_net_incremental_profit_(assumed_cost)": round(promos["net_incremental_profit"].sum(), 0),
        "total_net_incremental_revenue": round(promos["net_incremental_revenue"].sum(), 0),
    })
    summ.to_csv(OUT / "promo_summary.csv", header=["value"])
    print("PROMO SUMMARY\n", summ.to_string(), "\n")

    # shallow promos vs deep clearance: blending them hides what each is doing
    promos["depth"] = pd.cut(promos["avg_discount"], [0, 0.30, 0.40, 1.0],
                             labels=["shallow (15-30%)", "medium (30-40%)", "deep clearance (>40%)"])
    depth = promos.groupby("depth", observed=True).agg(
        products=("stock_code", "count"),
        median_lift_pct=("promo_lift", lambda x: round(100 * x.median(), 0)),
        median_post_dip_pct=("post_dip", lambda x: round(100 * x.median(), 1)),
        pct_revenue_positive=("net_incremental_revenue", lambda x: round(100 * (x > 0).mean(), 1)),
        pct_profit_positive=("net_incremental_profit", lambda x: round(100 * (x > 0).mean(), 1)),
        net_revenue=("net_incremental_revenue", "sum"),
        net_profit_assumed_cost=("net_incremental_profit", "sum"),
    ).round(0)
    depth.to_csv(OUT / "promo_by_depth.csv")
    print("PROMOS BY DEPTH\n", depth.to_string(), "\n")

    el = pd.read_csv(OUT / "elasticity_by_product.csv", dtype={"stock_code": str})
    seg = segment(el, promos)
    seg.to_csv(OUT / "segments.csv", index=False)
    ss = seg.groupby("segment").agg(
        products=("stock_code", "count"),
        median_elasticity=("elasticity_robust", "median"),
        annual_profit_impact=("annual_profit_impact", "sum"),
    ).round(2)
    ss.to_csv(OUT / "segment_summary.csv")
    print("SEGMENTS (cost assumed at", int(COST_RATIO * 100), "% of price)\n", ss.to_string())
    print("\nconfident 'Raise price':", int((seg["confident"] == True).sum()), "of", int((seg["segment"] == "Raise price").sum()))

    # sensitivity of segment counts to the cost assumption
    print("\nSENSITIVITY: raise / discount counts by assumed cost ratio")
    for cr in (0.5, 0.6, 0.7):
        th = 1 / (1 - cr)
        a = seg["elasticity_robust"].abs()
        up = (seg["reliable"] & (a < th)).sum()
        dn = (seg["reliable"] & (a > th) & (seg["net_incremental_profit"].fillna(-1) > 0)).sum()
        print(f"  cost={int(cr*100)}%: raise={up}, discount={dn}")


if __name__ == "__main__":
    main()
