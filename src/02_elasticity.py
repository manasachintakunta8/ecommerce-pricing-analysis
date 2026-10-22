"""Price elasticity per product via log-log regression on weekly data, two ways.

  naive : weekly price = revenue / quantity over ALL order lines
  robust: weekly price = quantity-weighted modal LIST price, using only retail-size lines
          (quantity <= BULK_QTY), so bulk-discount orders cannot create a fake
          price-down / quantity-up relationship.

Model per product:  ln(qty_wk) = a + b * ln(price_wk) + month fixed effects ;  b = elasticity.
Products are skipped if they have too few weeks, too little price variation,
a rank-deficient design matrix, or too few residual degrees of freedom.
"""
import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "retail.db"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

MIN_WEEKS = 30
MIN_PRICE_CV = 0.05
BULK_QTY = 24  # order lines above this are treated as wholesale and excluded from the robust model


def modal_price(g):
    """Quantity-weighted most common unit price in the group."""
    return g.groupby("unit_price")["quantity"].sum().idxmax()


def weekly_naive(df):
    w = df.groupby(["stock_code", "week"]).agg(
        description=("description", "max"), qty=("quantity", "sum"), rev=("revenue", "sum")
    ).reset_index()
    w["price"] = w["rev"] / w["qty"]
    return w[["stock_code", "description", "week", "qty", "price"]]


def weekly_robust(df):
    d = df[df["quantity"] <= BULK_QTY]
    qty = d.groupby(["stock_code", "week"]).agg(description=("description", "max"), qty=("quantity", "sum"))
    price = (
        d.groupby(["stock_code", "week", "unit_price"])["quantity"].sum().reset_index()
        .sort_values("quantity").drop_duplicates(["stock_code", "week"], keep="last")
        .set_index(["stock_code", "week"])["unit_price"].rename("price")
    )
    return qty.join(price).reset_index()


def fit_products(weekly, label):
    weekly = weekly.assign(month=pd.to_datetime(weekly["week"]).dt.month)
    rows = []
    for code, g in weekly.groupby("stock_code"):
        if len(g) < MIN_WEEKS or g["price"].std() / g["price"].mean() < MIN_PRICE_CV:
            continue
        g = g.assign(ln_q=np.log(g["qty"]), ln_p=np.log(g["price"]))
        X = pd.get_dummies(g["month"], prefix="m", drop_first=True).astype(float)
        X.insert(0, "ln_p", g["ln_p"].to_numpy())
        X.insert(0, "const", 1.0)
        if np.linalg.matrix_rank(X.to_numpy()) < X.shape[1] or len(g) - X.shape[1] < 10:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = smf.ols("ln_q ~ ln_p + C(month)", data=g).fit()
        if not np.isfinite(m.bse["ln_p"]):
            continue
        rows.append(dict(
            method=label, stock_code=code, description=g["description"].iloc[0], weeks=len(g),
            mean_price=g["price"].mean(), total_qty=g["qty"].sum(),
            elasticity=m.params["ln_p"], std_err=m.bse["ln_p"], p_value=m.pvalues["ln_p"], r2=m.rsquared,
        ))
    res = pd.DataFrame(rows)
    res["significant"] = res["p_value"] < 0.05
    return res


def main():
    with sqlite3.connect(DB) as con:
        df = pd.read_sql("SELECT stock_code, description, week, quantity, unit_price, revenue FROM transactions", con)

    naive = fit_products(weekly_naive(df), "naive")
    robust = fit_products(weekly_robust(df), "robust")
    res = pd.concat([naive, robust], ignore_index=True)
    res.to_csv(OUT / "elasticity_by_product.csv", index=False)

    summary = (
        res.groupby("method")
        .apply(lambda r: pd.Series({
            "products": len(r),
            "significant": int(r["significant"].sum()),
            "pct_significant": round(100 * r["significant"].mean(), 1),
            "median_elasticity_sig": round(r.loc[r["significant"], "elasticity"].median(), 2),
            "p25": round(r.loc[r["significant"], "elasticity"].quantile(0.25), 2),
            "p75": round(r.loc[r["significant"], "elasticity"].quantile(0.75), 2),
            "pct_sig_positive": round(100 * (r.loc[r["significant"], "elasticity"] > 0).mean(), 1),
        }), include_groups=False)
    )
    summary.to_csv(OUT / "elasticity_summary.csv")
    print(summary.T.to_string())

    both = naive.merge(robust, on="stock_code", suffixes=("_naive", "_robust"))
    print(f"\nproducts in both methods: {len(both):,}")
    print(f"correlation of elasticities: {both['elasticity_naive'].corr(both['elasticity_robust']):.2f}")


if __name__ == "__main__":
    main()
