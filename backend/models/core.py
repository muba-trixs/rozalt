"""Master and operational data: products, regions, demand, inventory, promotions, events."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class Product(Base):
    __tablename__ = "products"
    sku_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Region(Base):
    __tablename__ = "regions"
    region_id: Mapped[str] = mapped_column(String(80), primary_key=True)  # canonical display name


class DemandRecord(Base):
    """Forecast (planned) and recorded sales (observed) — never treated as underlying demand."""

    __tablename__ = "demand_records"
    __table_args__ = (UniqueConstraint("date", "sku_id", "region_id", name="uq_demand_day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("products.sku_id"), index=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.region_id"), index=True)
    forecast_qty: Mapped[float] = mapped_column(Float)
    recorded_sales_qty: Mapped[float] = mapped_column(Float)


class InventoryRecord(Base):
    __tablename__ = "inventory_records"
    __table_args__ = (UniqueConstraint("date", "sku_id", "region_id", name="uq_inventory_day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("products.sku_id"), index=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.region_id"), index=True)
    available_inventory: Mapped[float] = mapped_column(Float)
    stockout_flag: Mapped[bool] = mapped_column(Boolean, default=False)


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (
        UniqueConstraint("start_date", "sku_id", "region_id", "promotion_type", name="uq_promotion"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_date: Mapped[dt.date] = mapped_column(Date, index=True)
    end_date: Mapped[dt.date] = mapped_column(Date)
    sku_id: Mapped[str] = mapped_column(ForeignKey("products.sku_id"), index=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.region_id"), index=True)
    promotion_type: Mapped[str] = mapped_column(String(80))
    discount_pct: Mapped[float] = mapped_column(Float)


class OperationalEvent(Base):
    __tablename__ = "operational_events"
    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    event_type: Mapped[str] = mapped_column(String(80))
    region_id: Mapped[str] = mapped_column(String(80), index=True)
    affected_facility: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    related_sku_ids: Mapped[list] = mapped_column(JSON, default=list)
    related_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)


class ExternalEvent(Base):
    __tablename__ = "external_events"
    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_date: Mapped[dt.date] = mapped_column(Date, index=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    event_title: Mapped[str] = mapped_column(String(300))
    event_description: Mapped[str] = mapped_column(Text, default="")
    event_category: Mapped[str] = mapped_column(String(80))
    region_id: Mapped[str] = mapped_column(String(80), index=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    related_sku_ids: Mapped[list] = mapped_column(JSON, default=list)
    related_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)


class DatasetImport(Base):
    __tablename__ = "dataset_imports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_type: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20))  # SUCCESS | PARTIAL | FAILED
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
