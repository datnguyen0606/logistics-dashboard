"""One-off CSV → PostgreSQL ingestion script. Run once at deploy: python -m backend.db.loader"""
import os
import pandas as pd
from sqlalchemy import create_engine, text
from backend.config import settings

SYNC_URL = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def load_csv_to_postgres(csv_path: str | None = None) -> None:
    path = csv_path or settings.CSV_PATH
    df = pd.read_csv(path, parse_dates=["order_date", "delivery_date"])

    # Drop generated columns — PostgreSQL computes them
    df = df.drop(columns=["delivery_days", "is_delayed"], errors="ignore")

    engine = create_engine(SYNC_URL)
    with engine.begin() as conn:
        df.to_sql("orders", conn, if_exists="replace", index=False, method="multi", chunksize=500)

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_order_date        ON orders(order_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_carrier           ON orders(carrier)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_status            ON orders(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_product_category  ON orders(product_category)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_region            ON orders(region)"))

        # Ensure the app user is read-only. Adjust username as needed.
        # conn.execute(text("GRANT SELECT ON orders TO app;"))

    print(f"Loaded {len(df)} rows into orders table.")


if __name__ == "__main__":
    load_csv_to_postgres()
