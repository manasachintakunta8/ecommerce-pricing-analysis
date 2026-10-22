"""Load UCI Online Retail II, clean it, and write a SQLite database.

Cleaning rules (each is logged so the README can report row counts):
  - drop rows without a product code or with non-product codes (postage, fees, samples)
  - drop cancellations (invoice starts with 'C') and non-positive quantity/price
  - drop exact duplicate rows
  - build revenue = quantity * unit price
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw" / "online_retail_II.xlsx"
DB = ROOT / "data" / "retail.db"
DB.parent.mkdir(exist_ok=True)

NON_PRODUCT = {"POST", "D", "M", "DOT", "CRUK", "BANK CHARGES", "AMAZONFEE", "S", "B", "ADJUST", "ADJUST2"}


def main():
    sheets = pd.read_excel(RAW, sheet_name=None, dtype={"Invoice": str, "StockCode": str})
    df = pd.concat(sheets.values(), ignore_index=True)
    df.columns = ["invoice", "stock_code", "description", "quantity", "invoice_date", "unit_price", "customer_id", "country"]
    log = [("raw rows", len(df))]

    df = df.drop_duplicates()
    log.append(("after dropping exact duplicates", len(df)))

    cancelled = df["invoice"].str.startswith("C", na=False)
    df = df[~cancelled]
    log.append(("after dropping cancellations", len(df)))

    df = df[(df["quantity"] > 0) & (df["unit_price"] > 0)]
    log.append(("after dropping qty<=0 / price<=0", len(df)))

    df["stock_code"] = df["stock_code"].str.upper().str.strip()
    is_product = df["stock_code"].apply(lambda s: bool(re.match(r"^\d{5}", str(s)))) & ~df["stock_code"].isin(NON_PRODUCT)
    df = df[is_product]
    log.append(("after dropping non-product codes", len(df)))

    df["description"] = df["description"].fillna("").str.strip().str.upper()
    df["revenue"] = df["quantity"] * df["unit_price"]
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    df["week"] = df["invoice_date"].dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")

    with sqlite3.connect(DB) as con:
        df.to_sql("transactions", con, if_exists="replace", index=False)
        pd.DataFrame(log, columns=["step", "rows"]).to_sql("cleaning_log", con, if_exists="replace", index=False)

    for step, n in log:
        print(f"{step:40s} {n:>10,}")
    print(f"\nwrote {DB}")


if __name__ == "__main__":
    main()
