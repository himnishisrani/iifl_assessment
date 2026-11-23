# Sales Dashboard (PostgreSQL + Streamlit)

An interactive sales dashboard built from two Excel files (`customers.xlsx`, `orders.xlsx`).
The data is loaded into PostgreSQL, joined through a SQL view, and shown in a Streamlit app.

## Tools used

- **PostgreSQL 16**: database
- **Python 3.12**: pandas and openpyxl (read and clean the Excel files), SQLAlchemy 2 with psycopg2 (database access)
- **Streamlit + Plotly**: dashboard
- **Docker Compose**: runs the database, loader and dashboard

## Project files

| File | Purpose |
|---|---|
| `schema.sql` | Table creation: `customers` and `orders`, with primary keys, the foreign key, constraints and indexes |
| `view.sql` | `v_sales` view: the joined dataset (orders joined to customers on `customer_id`) |
| `load_data.py` | Reads, cleans and loads both Excel files into PostgreSQL, then creates the view |
| `app.py` | Streamlit dashboard, reading from `v_sales` |
| `requirements.txt` | Python dependencies |
| `Dockerfile`, `docker-compose.yml` | Containerised setup |
| `data/` | `customers.xlsx` and `orders.xlsx` |

## Data model

- `customers.customer_id` is the **primary key**.
- `orders.order_id` is the primary key; `orders.customer_id` is a **NOT NULL foreign key** to `customers.customer_id`.
- One customer can have many orders.
- Data types: dates are `DATE`, money is `NUMERIC(12,2)`, discount is `NUMERIC(5,4)` (stored as a fraction, so 10% is 0.10), quantity is `INTEGER`.
- `v_sales` uses an inner `JOIN` on `customer_id`. Because of the foreign key, every order matches exactly one customer, so the join cannot drop or duplicate orders. It also adds an `order_month` column for the monthly trend.

## Setup and run (Docker)

Requires Docker Desktop. Put `customers.xlsx` and `orders.xlsx` in the `data/` folder, then, from the project folder:

```bash
docker compose up -d db            # 1. start PostgreSQL
docker compose run --rm loader     # 2. create tables, load data, create the view
docker compose up --build app      # 3. start the dashboard
```

Open http://localhost:8501.

Run step 2 before step 3, because the dashboard reads the `v_sales` view that the loader creates. Re-running the loader is safe: it truncates both tables and reloads them.

If you change the code (not just the data), rebuild first with `docker compose build loader`.

## Setup and run (without Docker for Python)

1. Start PostgreSQL only: `docker compose up -d db` (or use any Postgres with a database `sales`, user `sales`, password `sales`).
2. `pip install -r requirements.txt`
3. `python load_data.py`
4. `streamlit run app.py`

To use a different database, set `DATABASE_URL`, for example
`postgresql+psycopg2://user:password@host:5432/dbname`.

## Dashboard contents

- **KPIs:** total net revenue, total orders, unique customers, average order value, repeat-customer rate (bonus)
- **Charts:** monthly revenue trend, revenue by product category, revenue by customer segment or city (switchable), order count by order status
- **Top 5 products** by net revenue (bonus)
- **Filters (sidebar):** order date range, product category, customer segment, city, order status

All filters feed a single filtered dataset, so the KPIs and charts always agree with each other.

## Metric definitions

- **Net revenue** = sum of `Net_Amount_INR` (cancelled orders are already 0).
- **Total orders** = count of distinct `Order_ID` (all statuses).
- **Unique customers** = count of distinct `Customer_ID`.
- **Average order value** = total net revenue / count of distinct **non-cancelled** orders.
- **Repeat customers** = customers with 2 or more non-cancelled orders / customers with at least 1 non-cancelled order.

## Data loaded

The loader reported 60 customers and 240 orders (164 Completed, 40 Returned, 36 Cancelled), with total net revenue of ₹1,159,206.


