"""API integration: load data → list anomalies → investigate → read report → feedback → reopen."""


def test_full_api_flow(client):
    r = client.post("/api/v1/datasets/load-synthetic")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["anomalies_detected"] > 0

    ov = client.get("/api/v1/analytics/overview").json()["data"]
    assert ov["kpis"]["skus_monitored"] == 24 and ov["kpis"]["active_anomalies"] > 0

    an = client.get("/api/v1/anomalies", params={"severity": "HIGH", "sort": "abs_variance",
                                                  "order": "desc", "page_size": 5}).json()
    assert an["meta"]["total"] >= 1
    target = an["data"][0]

    ts = client.get("/api/v1/analytics/timeseries",
                    params={"sku_id": target["sku_id"], "region": target["region"]}).json()["data"]
    assert {"forecast_qty", "recorded_sales_qty", "seasonal_baseline"} <= set(ts["points"][0])
    assert ts["anomalies"]

    r = client.post("/api/v1/investigations", json={"anomaly_id": target["anomaly_id"], "use_llm": False})
    assert r.status_code == 202
    inv_id = r.json()["data"]["investigation_id"]

    rep = client.get(f"/api/v1/investigations/{inv_id}").json()["data"]
    assert rep["status"] == "COMPLETED", rep["error"]
    assert rep["analysis_mode"] == "deterministic"
    assert [s["status"] for s in rep["stage_log"]] == ["completed"] * 9
    assert rep["hypotheses"] and rep["evidence"] and rep["candidates"]
    ids = {e["evidence_id"] for e in rep["evidence"]}
    for h in rep["hypotheses"]:
        assert set(h["supporting_evidence_ids"]) <= ids

    h_id = rep["hypotheses"][0]["id"]
    fb = client.post(f"/api/v1/hypotheses/{h_id}/feedback", json={"verdict": "CONFIRMED", "note": "Verified"})
    assert fb.status_code == 201
    bad = client.post(f"/api/v1/hypotheses/{h_id}/feedback", json={"verdict": "MAYBE"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"

    again = client.get(f"/api/v1/investigations/{inv_id}").json()["data"]
    assert again["hypotheses"][0]["feedback"][0]["verdict"] == "CONFIRMED"

    lst = client.get("/api/v1/investigations").json()["data"]
    assert lst[0]["investigation_id"] == inv_id
    assert client.get(f"/api/v1/anomalies/{target['anomaly_id']}").json()["data"]["status"] == "INVESTIGATED"

    ev = client.get("/api/v1/events", params={"q": "strike"}).json()
    assert any(e["event_id"] == "OPS-3001" for e in ev["data"])
    assert client.get("/api/v1/events/OPS-3001").json()["data"]["source_type"] == "operational"


def test_upload_preview_and_import(client):
    csv = b"date,sku_id,product_name,region,forecast_quantity,actual_sales_quantity\n2026-01-01,SKU-X,Thing,Goa,10,9\n"
    p = client.post("/api/v1/datasets/demand/preview", files={"file": ("d.csv", csv, "text/csv")}).json()["data"]
    assert p["rows_valid"] == 1 and p["preview"][0]["sku_id"] == "SKU-X"
    i = client.post("/api/v1/datasets/demand/import", files={"file": ("d.csv", csv, "text/csv")}).json()["data"]
    assert i["status"] == "SUCCESS" and i["rows_imported"] == 1
    hist = client.get("/api/v1/datasets/imports").json()["data"]
    assert hist[0]["filename"] == "d.csv"
    assert client.post("/api/v1/datasets/nope/import", files={"file": ("d.csv", csv)}).status_code == 404


def test_settings_validation(client):
    s = client.get("/api/v1/settings").json()["data"]
    assert abs(sum(s["relevance"]["weights"].values()) - 1) < 1e-9
    bad = client.put("/api/v1/settings/relevance/weights", json={"temporal": 1.0})
    assert bad.status_code == 400
    ok = client.put("/api/v1/settings/detection", json={"z_threshold": 3.5}).json()["data"]
    assert ok["detection"]["z_threshold"] == 3.5
