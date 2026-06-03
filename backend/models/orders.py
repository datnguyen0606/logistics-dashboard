from sqlalchemy import Column, Integer, Text, Date, Numeric, Boolean
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    order_id           = Column(Text, primary_key=True)
    client_id          = Column(Text, nullable=False)
    order_date         = Column(Date, nullable=False)
    delivery_date      = Column(Date)
    carrier            = Column(Text, nullable=False)
    origin_city        = Column(Text)
    destination_city   = Column(Text)
    status             = Column(Text, nullable=False)
    sku                = Column(Text)
    product_category   = Column(Text)
    quantity           = Column(Integer)
    unit_price_usd     = Column(Numeric(10, 2))
    order_value_usd    = Column(Numeric(10, 2))
    is_promo           = Column(Boolean)
    promo_discount_pct = Column(Integer)
    region             = Column(Text)
    warehouse          = Column(Text)
    # Generated/computed columns — read-only at runtime
    delivery_days      = Column(Integer)
    is_delayed         = Column(Boolean)
