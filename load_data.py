"""
Reads customers.xlsx and orders.xlsx, cleans them, and loads them into PostgreSQL.

"""
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent
DB_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://sales:sales@localhost:5432/sales")

CUSTOMER_COLS = ["Customer_ID", "Customer_Name", "Email", "City", "State",
                 "Customer_Segment", "Join_Date", "Acquisition_Channel"]
ORDER_COLS = ["Order_ID", "Customer_ID", "Order_Date", "Product_ID", "Product_Name",
              "Category", "Quantity", "Unit_Price_INR", "Discount_Rate",
              "Net_Amount_INR", "Payment_Method", "Order_Status"]

DATE_FORMAT = "%d-%b-%Y"  


def find_file(name: str) -> Path:
    folders = [Path(os.getenv("DATA_DIR", ROOT / "data")), ROOT]
    for folder in folders:
        if (folder / name).exists():
            return folder / name
    sys.exit(f"Could not find {name} in: {[str(f) for f in folders]}")


def read_excel(name: str, expected: list[str]) -> pd.DataFrame:
    df = pd.read_excel(find_file(name), dtype=object)  
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        sys.exit(f"{name}: missing columns {missing}. Found: {list(df.columns)}")
    return df[expected].copy()


def clean_text(s: pd.Series) -> pd.Series:
    s = s.astype("string").str.strip()
    return s.mask(s == "")  

def to_number(s: pd.Series) -> pd.Series:
    """'₹1,799' -> 1799.0 ; numeric cells pass through unchanged."""
    cleaned = (s.astype("string")
                .str.replace("₹", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip())
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def to_fraction(s: pd.Series) -> pd.Series:
    """'10%' -> 0.10 ; 0.1 -> 0.1 ; 10 -> 0.10 (values above 1 are treated as percents)."""
    as_text = s.astype("string").str.strip()
    is_pct_text = as_text.str.endswith("%", na=False)
    nums = pd.to_numeric(as_text.str.rstrip("%"), errors="coerce").astype("float64")
    nums = nums.where(~is_pct_text, nums / 100)          # text like '10%'
    nums = nums.where(is_pct_text | (nums <= 1), nums / 100)  # bare 10 -> 0.10
    return nums


def to_date(s: pd.Series) -> pd.Series:
    """Parse '10-Jun-2025'; fall back to generic parsing for real Excel dates."""
    parsed = pd.to_datetime(s, format=DATE_FORMAT, errors="coerce")
    fallback = pd.to_datetime(s[parsed.isna()], errors="coerce", dayfirst=True)
    parsed = parsed.fillna(fallback)
    return parsed.dt.date.where(parsed.notna(), None)


# ---------------------------------------------------------------- cleaning
def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["Customer_ID", "Customer_Name", "Email", "City", "State",
              "Customer_Segment", "Acquisition_Channel"]:
        df[c] = clean_text(df[c])
    df["Customer_ID"] = df["Customer_ID"].str.upper()
    df["Email"] = df["Email"].str.lower()
    df["Join_Date"] = to_date(df["Join_Date"])

    before = len(df)
    df = df.dropna(subset=["Customer_ID", "Customer_Name"])
    df = df.drop_duplicates(subset="Customer_ID", keep="first")
    print(f"customers: {before} rows read -> {len(df)} kept "
          f"({before - len(df)} null/duplicate removed)")
    return df


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["Order_ID", "Customer_ID", "Product_ID", "Product_Name",
              "Category", "Payment_Method", "Order_Status"]:
        df[c] = clean_text(df[c])
    df["Order_ID"] = df["Order_ID"].str.upper()
    df["Customer_ID"] = df["Customer_ID"].str.upper()
    df["Product_ID"] = df["Product_ID"].str.upper()
    df["Order_Status"] = df["Order_Status"].str.title()

    df["Order_Date"] = to_date(df["Order_Date"])
    df["Quantity"] = to_number(df["Quantity"])
    df["Unit_Price_INR"] = to_number(df["Unit_Price_INR"])
    df["Discount_Rate"] = to_fraction(df["Discount_Rate"]).fillna(0)
    df["Net_Amount_INR"] = to_number(df["Net_Amount_INR"])

    before = len(df)
    required = ["Order_ID", "Customer_ID", "Order_Date", "Quantity",
                "Unit_Price_INR", "Net_Amount_INR", "Order_Status"]
    df = df.dropna(subset=required)
    df = df.drop_duplicates(subset="Order_ID", keep="first")
    df["Quantity"] = df["Quantity"].astype(int)
    print(f"orders: {before} rows read -> {len(df)} kept "
          f"({before - len(df)} null/duplicate removed)")

    # Business rule: cancelled orders have a net amount of zero
    bad = (df["Order_Status"] == "Cancelled") & (df["Net_Amount_INR"] != 0)
    if bad.any():
        print(f"WARNING: {bad.sum()} cancelled orders had a non-zero net amount; set to 0")
        df.loc[bad, "Net_Amount_INR"] = 0
    return df


# ---------------------------------------------------------------- load
def main() -> None:
    customers = clean_customers(read_excel("customers.xlsx", CUSTOMER_COLS))
    orders = clean_orders(read_excel("orders.xlsx", ORDER_COLS))

    # Foreign-key check: orders must point at an existing customer
    orphans = ~orders["Customer_ID"].isin(customers["Customer_ID"])
    if orphans.any():
        print(f"WARNING: dropping {orphans.sum()} orders with unknown Customer_ID: "
              f"{sorted(orders.loc[orphans, 'Customer_ID'].unique())[:10]}")
        orders = orders[~orphans]

    # DB column names are lower-case
    customers.columns = [c.lower() for c in customers.columns]
    orders.columns = [c.lower() for c in orders.columns]
    print("order statuses:", orders["order_status"].value_counts().to_dict())

    engine = create_engine(DB_URL)
    with engine.begin() as conn:  # one transaction: all-or-nothing
        conn.exec_driver_sql((ROOT / "schema.sql").read_text())
        conn.execute(text("TRUNCATE TABLE orders, customers"))
        customers.to_sql("customers", conn, if_exists="append", index=False,
                         method="multi", chunksize=500)
        orders.to_sql("orders", conn, if_exists="append", index=False,
                      method="multi", chunksize=500)
        conn.exec_driver_sql((ROOT / "view.sql").read_text())

    with engine.connect() as conn:
        n_c = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        n_o, rev = conn.execute(
            text("SELECT COUNT(*), SUM(net_amount_inr) FROM v_sales")).one()
    print(f"Loaded {n_c} customers and {n_o} orders; total net revenue = INR {rev:,.2f}")


if __name__ == "__main__":
    main()