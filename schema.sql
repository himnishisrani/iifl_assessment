CREATE TABLE IF NOT EXISTS customers (
    customer_id         VARCHAR(10)  PRIMARY KEY,
    customer_name       VARCHAR(100) NOT NULL,
    email               VARCHAR(150),
    city                VARCHAR(60),
    state               VARCHAR(60),
    customer_segment    VARCHAR(30),
    join_date           DATE,
    acquisition_channel VARCHAR(30)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        VARCHAR(10)   PRIMARY KEY,
    customer_id     VARCHAR(10)   NOT NULL
                    REFERENCES customers (customer_id),
    order_date      DATE          NOT NULL,
    product_id      VARCHAR(10),
    product_name    VARCHAR(100),
    category        VARCHAR(50),
    quantity        INTEGER       NOT NULL CHECK (quantity >= 0),
    unit_price_inr  NUMERIC(12,2) NOT NULL CHECK (unit_price_inr >= 0),
 
    discount_rate   NUMERIC(5,4)  NOT NULL DEFAULT 0
                    CHECK (discount_rate >= 0 AND discount_rate <= 1),
    net_amount_inr  NUMERIC(12,2) NOT NULL CHECK (net_amount_inr >= 0),
    payment_method  VARCHAR(30),
    order_status    VARCHAR(20)   NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_order_date  ON orders (order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders (order_status);