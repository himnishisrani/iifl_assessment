import os

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine

DB_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://sales:sales@localhost:5432/sales")

st.set_page_config(page_title="Sales Dashboard", layout="wide")


@st.cache_resource
def get_engine():
    return create_engine(DB_URL, pool_pre_ping=True)


@st.cache_data(ttl=300)
def load_sales() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql("SELECT * FROM v_sales", conn)
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["order_month"] = pd.to_datetime(df["order_month"])
    df["net_amount_inr"] = df["net_amount_inr"].astype(float)
    return df


try:
    df = load_sales()
except Exception as exc:  # DB down, view missing, etc.
    st.error(f"Could not read v_sales from the database.\n\n{exc}")
    st.info("Check DATABASE_URL and run `python load_data.py` first.")
    st.stop()

if df.empty:
    st.warning("v_sales is empty. Run `python load_data.py` first.")
    st.stop()

inr = lambda x: f"₹{x:,.0f}"

st.title("Sales Dashboard")

# ---------------------------------------------------------------- filters
st.sidebar.header("Filters")

min_d, max_d = df["order_date"].min().date(), df["order_date"].max().date()
picked = st.sidebar.date_input("Order date range", (min_d, max_d),
                               min_value=min_d, max_value=max_d)
if len(picked) != 2:
    st.info("Select an end date to apply the date range.")
    st.stop()
start, end = picked


def multiselect(label: str, column: str) -> list:
    options = sorted(df[column].dropna().unique())
    return st.sidebar.multiselect(label, options, default=options)


categories = multiselect("Product category", "category")
segments = multiselect("Customer segment", "customer_segment")
cities = multiselect("City", "city")
statuses = multiselect("Order status", "order_status")

# One filtered dataframe feeds every KPI and chart, so they always agree.
f = df[
    df["order_date"].between(pd.Timestamp(start), pd.Timestamp(end))
    & df["category"].isin(categories)
    & df["customer_segment"].isin(segments)
    & df["city"].isin(cities)
    & df["order_status"].isin(statuses)
]

if f.empty:
    st.warning("No orders match the selected filters.")
    st.stop()

active = f[f["order_status"] != "Cancelled"]  # non-cancelled orders

# ---------------------------------------------------------------- KPIs
revenue = f["net_amount_inr"].sum()
total_orders = f["order_id"].nunique()
unique_customers = f["customer_id"].nunique()
active_orders = active["order_id"].nunique()
aov = revenue / active_orders if active_orders else 0

orders_per_customer = active.groupby("customer_id")["order_id"].nunique()
repeat_rate = (orders_per_customer > 1).mean() if len(orders_per_customer) else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total net revenue", inr(revenue))
k2.metric("Total orders", f"{total_orders:,}")
k3.metric("Unique customers", f"{unique_customers:,}")
k4.metric("Average order value", inr(aov), help="Net revenue / non-cancelled orders")
k5.metric("Repeat customers", f"{repeat_rate:.0%}",
          help="Customers with 2+ non-cancelled orders / customers with 1+")

returned = f[f["order_status"] == "Returned"]
st.caption(f"Returned orders in view: {returned['order_id'].nunique():,} "
           f"(worth {inr(returned['net_amount_inr'].sum())}, included in revenue). "
           f"Use the Order status filter to include or exclude them.")

# ---------------------------------------------------------------- charts
left, right = st.columns(2)

monthly = (f.groupby("order_month", as_index=False)["net_amount_inr"].sum()
             .sort_values("order_month"))
fig = px.line(monthly, x="order_month", y="net_amount_inr", markers=True,
              title="Monthly net revenue",
              labels={"order_month": "Month", "net_amount_inr": "Net revenue (₹)"})
fig.update_xaxes(dtick="M1", tickformat="%b %Y")
left.plotly_chart(fig)

by_cat = (f.groupby("category", as_index=False)["net_amount_inr"].sum()
            .sort_values("net_amount_inr", ascending=False))
right.plotly_chart(px.bar(by_cat, x="category", y="net_amount_inr",
                          title="Revenue by product category",
                          labels={"category": "Category", "net_amount_inr": "Net revenue (₹)"}))

left2, right2 = st.columns(2)

dim_label = left2.radio("Revenue by", ["Customer segment", "City"], horizontal=True)
dim = "customer_segment" if dim_label == "Customer segment" else "city"
by_dim = (f.groupby(dim, as_index=False)["net_amount_inr"].sum()
            .sort_values("net_amount_inr", ascending=False))
left2.plotly_chart(px.bar(by_dim, x=dim, y="net_amount_inr",
                          title=f"Revenue by {dim_label.lower()}",
                          labels={dim: dim_label, "net_amount_inr": "Net revenue (₹)"}))

by_status = (f.groupby("order_status", as_index=False)["order_id"].nunique()
               .rename(columns={"order_id": "orders"})
               .sort_values("orders", ascending=False))
right2.plotly_chart(px.bar(by_status, x="order_status", y="orders", text="orders",
                           title="Order count by status",
                           labels={"order_status": "Status", "orders": "Orders"}))

st.subheader("Top 5 products by net revenue")
top5 = (f.groupby("product_name", as_index=False)
          .agg(net_revenue=("net_amount_inr", "sum"),
               orders=("order_id", "nunique"))
          .nlargest(5, "net_revenue"))
top5["net_revenue"] = top5["net_revenue"].map(inr)
top5.columns = ["Product", "Net revenue", "Orders"]
st.dataframe(top5, hide_index=True)