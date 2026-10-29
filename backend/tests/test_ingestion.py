from backend import models as M
from backend.services import ingestion_service as ingest

DEMAND = b"""date,sku_id,product_name,region,forecast_quantity,actual_sales_quantity
2026-01-01,SKU-1,Widget,Maharashtra,100,90
02/01/2026,sku-1,Widget,maharashtra,100,95
2026-01-03,SKU-1,Widget,Maharashtra,abc,90
2026-01-04,SKU-1,Widget,Maharashtra,-5,90
2026-01-01,SKU-1,Widget,Maharashtra,100,90
not-a-date,SKU-1,Widget,Maharashtra,100,90
"""


def test_missing_columns_is_fatal(db):
    res = ingest.import_csv_bytes(db, "demand", b"date,sku_id\n2026-01-01,SKU-1\n", "x.csv")
    assert res["status"] == "FAILED"
    assert "forecast_quantity" in res["missing_columns"]


def test_validation_normalisation_and_duplicates(db):
    res = ingest.import_csv_bytes(db, "demand", DEMAND, "d.csv")
    assert res["rows_total"] == 6
    assert res["rows_rejected"] == 3  # non-numeric, negative, bad date
    assert res["rows_duplicate_in_file"] == 1
    assert res["rows_imported"] == 2
    assert res["status"] == "PARTIAL"
    msgs = {e["message"] for e in res["errors"]}
    assert "Value is not numeric" in msgs and "Value must be non-negative" in msgs
    dates = sorted(r.date.isoformat() for r in db.query(M.DemandRecord))
    assert dates == ["2026-01-01", "2026-01-02"]  # DD/MM/YYYY normalised
    regions = [r.region_id for r in db.query(M.Region)]
    assert regions == ["Maharashtra"]

    again = ingest.import_csv_bytes(db, "demand", DEMAND, "d.csv")
    assert again["rows_imported"] == 0 and again["rows_duplicate_in_db"] == 2


def test_inventory_requires_known_sku(db):
    ingest.import_csv_bytes(db, "demand", DEMAND, "d.csv")
    inv = b"date,sku_id,region,available_inventory,stockout_flag\n2026-01-01,SKU-1,Maharashtra,50,no\n2026-01-01,SKU-9,Maharashtra,50,maybe\n"
    res = ingest.import_csv_bytes(db, "inventory", inv, "i.csv")
    assert res["rows_imported"] == 1 and res["rows_rejected"] == 1
    assert db.query(M.InventoryRecord).one().stockout_flag is False


def test_promotion_date_order(db):
    ingest.import_csv_bytes(db, "demand", DEMAND, "d.csv")
    promo = b"start_date,end_date,sku_id,region,promotion_type,discount_percentage\n2026-01-05,2026-01-01,SKU-1,Maharashtra,Price,10\n2026-01-01,2026-01-05,SKU-1,Maharashtra,Price,150\n"
    res = ingest.import_csv_bytes(db, "promotions", promo, "p.csv")
    assert res["rows_rejected"] == 2


def test_synthetic_load_imports_everything(db):
    from backend.services.synthetic_loader import load_synthetic

    res = load_synthetic(db)
    assert all(i["status"] == "SUCCESS" for i in res["imports"])
    assert db.query(M.DemandRecord).count() == 24 * 5 * 365
    assert db.query(M.ExternalEvent).filter_by(event_id="EXT-2001").one().related_category == "Beverages"
    assert res["anomalies_detected"] > 0
