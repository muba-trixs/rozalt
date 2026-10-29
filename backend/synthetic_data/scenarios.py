"""Catalog, regions and injected evaluation scenarios for the synthetic dataset.

Ground truth defined here is written to ``ground_truth.json`` for the evaluator only.
The investigation engine never imports this module.
"""
from __future__ import annotations

import datetime as dt

START_DATE = dt.date(2025, 10, 1)
END_DATE = dt.date(2026, 9, 30)
SEED = 42

BRAND = "Aurora"

# sku_id, product_name, category, base daily units (national)
CATALOG: list[tuple[str, str, str, int]] = [
    ("SKU-101", "Citrus Fizz 500ml", "Beverages", 2600),
    ("SKU-102", "Cola Classic 1L", "Beverages", 3100),
    ("SKU-103", "Mango Nectar 1L", "Beverages", 1700),
    ("SKU-104", "Lemon Iced Tea 500ml", "Beverages", 1200),
    ("SKU-201", "Masala Crisps 90g", "Snacks", 2900),
    ("SKU-202", "Salted Peanuts 200g", "Snacks", 1500),
    ("SKU-203", "Bhujia Mix 400g", "Snacks", 1300),
    ("SKU-204", "Cheese Puffs 60g", "Snacks", 2100),
    ("SKU-301", "Instant Noodles 4-Pack", "Packaged Foods", 3400),
    ("SKU-302", "Basmati Rice 5kg", "Packaged Foods", 900),
    ("SKU-303", "Modak Mix 500g", "Packaged Foods", 600),
    ("SKU-304", "Pure Ghee 1L", "Packaged Foods", 1100),
    ("SKU-401", "Fresh Curd 400g", "Dairy", 2400),
    ("SKU-402", "Toned Milk 1L", "Dairy", 4200),
    ("SKU-403", "Malai Paneer 200g", "Dairy", 1400),
    ("SKU-404", "Flavoured Yogurt 100g", "Dairy", 1600),
    ("SKU-501", "Herbal Shampoo 340ml", "Personal Care", 1000),
    ("SKU-502", "Neem Soap 4-Pack", "Personal Care", 1800),
    ("SKU-503", "Clove Toothpaste 150g", "Personal Care", 2000),
    ("SKU-504", "Aloe Face Wash 100ml", "Personal Care", 800),
    ("SKU-601", "Detergent Powder 1kg", "Home Care", 2200),
    ("SKU-602", "Dishwash Liquid 500ml", "Home Care", 1600),
    ("SKU-603", "Floor Cleaner 1L", "Home Care", 1000),
    ("SKU-604", "Toilet Cleaner 500ml", "Home Care", 900),
]

REGIONS: dict[str, float] = {
    "Maharashtra": 1.30,
    "Telangana": 0.80,
    "Karnataka": 1.00,
    "Tamil Nadu": 0.95,
    "Delhi NCR": 1.10,
}

FACILITIES: dict[str, list[str]] = {
    "Maharashtra": ["DC-MUM-01", "DC-PUN-02"],
    "Telangana": ["DC-HYD-01"],
    "Karnataka": ["DC-BLR-01"],
    "Tamil Nadu": ["DC-CHN-01", "PLANT-CHN-02"],
    "Delhi NCR": ["DC-DEL-01"],
}

# Annual seasonality: (amplitude, peak day-of-year)
SEASONALITY: dict[str, tuple[float, int]] = {
    "Beverages": (0.22, 135),
    "Snacks": (0.06, 295),
    "Packaged Foods": (0.04, 300),
    "Dairy": (0.08, 140),
    "Personal Care": (0.03, 120),
    "Home Care": (0.05, 290),
}

# Known national holiday that planners include in the forecast (Diwali 2025)
KNOWN_HOLIDAYS = [
    {"start": dt.date(2025, 10, 15), "end": dt.date(2025, 10, 20), "lift": 0.12,
     "categories": ["Snacks", "Packaged Foods", "Home Care"]},
]


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


# ---------------------------------------------------------------------------
# Scenario definitions
#   demand_effects : multiplicative effect on true (unconstrained) demand — NOT known to the forecast
#   supply_effects : caps inventory at `coverage` × demand → recorded sales fall, stockouts appear
#   promo_true_lift_multiplier : realised promo lift vs planned lift (multi-explanation case)
# ---------------------------------------------------------------------------
SCENARIOS: list[dict] = [
    {
        "scenario_id": "SCN-1",
        "name": "Competitor promotion (Karnataka beverages)",
        "region": "Karnataka",
        "window": (d("2026-04-13"), d("2026-04-26")),
        "direction": "NEGATIVE",
        "demand_effects": [
            {"sku_id": "SKU-102", "start": d("2026-04-13"), "end": d("2026-04-26"), "effect": -0.22},
            {"sku_id": "SKU-101", "start": d("2026-04-13"), "end": d("2026-04-26"), "effect": -0.07},
        ],
        "affected_skus": ["SKU-102"],
        "primary_event_ids": ["EXT-2001"],
        "acceptable_drivers": [{"driver_type": "competitor_activity", "event_id": "EXT-2001"}],
        "confounders": ["EXT-2002 (wrong region/category)", "EXT-2003 (national sporting event, opposite direction)"],
        "expected_outcome": "driver",
    },
    {
        "scenario_id": "SCN-2",
        "name": "Transport strike (Telangana DC-HYD-01)",
        "region": "Telangana",
        "window": (d("2026-06-09"), d("2026-06-15")),
        "direction": "NEGATIVE",
        "supply_effects": [
            {"sku_id": s, "start": d("2026-06-09"), "end": d("2026-06-15"), "coverage": c}
            for s, c in [("SKU-101", 0.62), ("SKU-102", 0.58), ("SKU-103", 0.66), ("SKU-104", 0.64),
                         ("SKU-201", 0.55), ("SKU-202", 0.63), ("SKU-203", 0.65), ("SKU-204", 0.60)]
        ],
        "affected_skus": ["SKU-101", "SKU-102", "SKU-103", "SKU-104", "SKU-201", "SKU-202", "SKU-203", "SKU-204"],
        "primary_event_ids": ["OPS-3001"],
        "acceptable_drivers": [{"driver_type": "distribution_disruption", "event_id": "OPS-3001"}],
        "confounders": ["Internal promotion on SKU-201 during strike (opposite direction)",
                        "EXT-2011 heavy-rain forecast after onset", "OPS-3002 routine maintenance 3 weeks earlier"],
        "expected_outcome": "driver",
    },
    {
        "scenario_id": "SCN-3",
        "name": "Regional festival (Ganeshotsav, Maharashtra)",
        "region": "Maharashtra",
        "window": (d("2026-09-12"), d("2026-09-24")),
        "direction": "POSITIVE",
        "demand_effects": [
            {"sku_id": "SKU-303", "start": d("2026-09-12"), "end": d("2026-09-24"), "effect": 0.45},
            {"sku_id": "SKU-304", "start": d("2026-09-12"), "end": d("2026-09-24"), "effect": 0.22},
            {"sku_id": "SKU-203", "start": d("2026-09-12"), "end": d("2026-09-24"), "effect": 0.24},
        ],
        "promo_true_lift_multiplier": {"SKU-304": 1.8},
        "affected_skus": ["SKU-303", "SKU-304", "SKU-203"],
        "primary_event_ids": ["EXT-2021"],
        "acceptable_drivers": [
            {"driver_type": "cultural_event", "event_id": "EXT-2021"},
            {"driver_type": "internal_promotion", "sku_id": "SKU-304"},
        ],
        "confounders": ["Internal promotion on SKU-304 overlaps the festival (multi-explanation)",
                        "EXT-2022 festival outside monitored regions"],
        "expected_outcome": "driver",
    },
    {
        "scenario_id": "SCN-4",
        "name": "Product quality incident (Tamil Nadu curd)",
        "region": "Tamil Nadu",
        "window": (d("2026-02-07"), d("2026-03-08")),
        "direction": "NEGATIVE",
        "demand_effects": [
            {"sku_id": "SKU-401", "start": d("2026-02-07"), "end": d("2026-03-08"), "effect": -0.18},
        ],
        "affected_skus": ["SKU-401"],
        "primary_event_ids": ["EXT-2031", "OPS-3021"],
        "acceptable_drivers": [
            {"driver_type": "product_quality", "event_id": "EXT-2031"},
            {"driver_type": "product_quality", "event_id": "OPS-3021"},
        ],
        "confounders": ["EXT-2032 competitor dairy promotion starting 10 days after onset"],
        "expected_outcome": "driver",
    },
    {
        "scenario_id": "SCN-5",
        "name": "Unexplained dip (Delhi NCR toothpaste)",
        "region": "Delhi NCR",
        "window": (d("2026-07-20"), d("2026-07-24")),
        "direction": "NEGATIVE",
        "demand_effects": [
            {"sku_id": "SKU-503", "start": d("2026-07-20"), "end": d("2026-07-24"), "effect": -0.27},
        ],
        "affected_skus": ["SKU-503"],
        "primary_event_ids": [],
        "acceptable_drivers": [],
        "confounders": ["EXT-2041 unrelated local event the day before"],
        "expected_outcome": "insufficient_evidence",
    },
    {
        "scenario_id": "SCN-6",
        "name": "Overlapping disruptions (Maharashtra floods + DC waterlogging)",
        "region": "Maharashtra",
        "window": (d("2026-07-06"), d("2026-07-12")),
        "direction": "NEGATIVE",
        "supply_effects": [
            {"sku_id": "SKU-601", "start": d("2026-07-06"), "end": d("2026-07-12"), "coverage": 0.62},
            {"sku_id": "SKU-602", "start": d("2026-07-06"), "end": d("2026-07-12"), "coverage": 0.60},
        ],
        "demand_effects": [
            {"sku_id": s, "start": d("2026-07-05"), "end": d("2026-07-09"), "effect": -0.05}
            for s, *_ in CATALOG
        ],
        "affected_skus": ["SKU-601", "SKU-602"],
        "primary_event_ids": ["OPS-3031"],
        "acceptable_drivers": [
            {"driver_type": "distribution_disruption", "event_id": "OPS-3031"},
            {"driver_type": "weather", "event_id": "EXT-2051"},
        ],
        "confounders": ["Weather and facility disruption overlap (two plausible explanations)"],
        "expected_outcome": "driver",
    },
]

# Planned internal promotions that are part of scenarios (confounders / multi-explanation)
SCENARIO_PROMOTIONS = [
    {"start_date": d("2026-06-05"), "end_date": d("2026-06-14"), "sku_id": "SKU-201", "region": "Telangana",
     "promotion_type": "Price Discount", "discount_percentage": 20.0},
    {"start_date": d("2026-09-10"), "end_date": d("2026-09-20"), "sku_id": "SKU-304", "region": "Maharashtra",
     "promotion_type": "Festive Bundle", "discount_percentage": 15.0},
]

SCENARIO_EXTERNAL_EVENTS = [
    {"event_id": "EXT-2001", "event_date": d("2026-04-10"), "end_date": d("2026-04-26"),
     "event_title": "FizzUp launches 30% off on carbonated soft drinks across Karnataka",
     "event_description": "Competitor brand FizzUp announced a statewide price promotion on 1L and 2L carbonated "
                          "soft drinks through modern trade and kirana distributors in Karnataka.",
     "event_category": "competitor_promotion", "region": "Karnataka", "source": "Retail Trade Bulletin",
     "source_url": "https://example.com/trade/fizzup-karnataka", "related_sku_ids": "",
     "related_category": "Beverages", "severity": "high"},
    {"event_id": "EXT-2002", "event_date": d("2026-04-08"), "end_date": d("2026-04-20"),
     "event_title": "CrunchCo cuts prices on potato chips in Delhi NCR",
     "event_description": "CrunchCo reduced MRP on 50g and 90g chip packs in Delhi NCR modern trade.",
     "event_category": "competitor_promotion", "region": "Delhi NCR", "source": "Retail Trade Bulletin",
     "source_url": "https://example.com/trade/crunchco-ncr", "related_sku_ids": "",
     "related_category": "Snacks", "severity": "medium"},
    {"event_id": "EXT-2003", "event_date": d("2026-03-28"), "end_date": d("2026-05-31"),
     "event_title": "Indian T20 cricket league season begins",
     "event_description": "National cricket league season starts; historically associated with higher "
                          "beverage and snack consumption during match evenings.",
     "event_category": "cultural_event", "region": "National", "source": "Sports Desk",
     "source_url": "https://example.com/sports/t20-season", "related_sku_ids": "",
     "related_category": "Beverages", "severity": "medium"},
    {"event_id": "EXT-2011", "event_date": d("2026-06-18"), "end_date": d("2026-06-20"),
     "event_title": "Heavy rainfall forecast for Hyderabad",
     "event_description": "IMD forecasts heavy rain over Hyderabad and surrounding districts.",
     "event_category": "weather", "region": "Telangana", "source": "IMD Bulletin",
     "source_url": "https://example.com/imd/hyd-rain", "related_sku_ids": "", "related_category": "",
     "severity": "low"},
    {"event_id": "EXT-2021", "event_date": d("2026-09-14"), "end_date": d("2026-09-24"),
     "event_title": "Ganeshotsav celebrations begin across Maharashtra",
     "event_description": "Ten-day Ganesh festival across Mumbai, Pune and Maharashtra; elevated household "
                          "purchases of festive foods such as modak, sweets, ghee and namkeen.",
     "event_category": "cultural_event", "region": "Maharashtra", "source": "Regional News Wire",
     "source_url": "https://example.com/news/ganeshotsav-2026", "related_sku_ids": "SKU-303;SKU-304",
     "related_category": "Packaged Foods;Snacks", "severity": "high"},
    {"event_id": "EXT-2022", "event_date": d("2026-08-26"), "end_date": d("2026-09-04"),
     "event_title": "Onam festival season in Kerala",
     "event_description": "Onam celebrations in Kerala with elevated festive food purchases.",
     "event_category": "cultural_event", "region": "Kerala", "source": "Regional News Wire",
     "source_url": "https://example.com/news/onam-2026", "related_sku_ids": "",
     "related_category": "Packaged Foods", "severity": "medium"},
    {"event_id": "EXT-2031", "event_date": d("2026-02-05"), "end_date": d("2026-02-20"),
     "event_title": "Surge in consumer complaints about sour taste of Aurora Fresh Curd",
     "event_description": "Consumer complaints portal and social media show a sharp rise in reports of sour "
                          "taste and early spoilage for Aurora Fresh Curd 400g in Chennai and Coimbatore.",
     "event_category": "product_quality", "region": "Tamil Nadu", "source": "Consumer Complaints Portal",
     "source_url": "https://example.com/complaints/aurora-curd", "related_sku_ids": "SKU-401",
     "related_category": "Dairy", "severity": "high"},
    {"event_id": "EXT-2032", "event_date": d("2026-02-17"), "end_date": d("2026-03-10"),
     "event_title": "MilkyWay Dairy launches buy-one-get-one on curd in Chennai",
     "event_description": "Competitor MilkyWay Dairy runs a BOGO offer on 400g curd cups in Chennai retail.",
     "event_category": "competitor_promotion", "region": "Tamil Nadu", "source": "Retail Trade Bulletin",
     "source_url": "https://example.com/trade/milkyway-bogo", "related_sku_ids": "",
     "related_category": "Dairy", "severity": "medium"},
    {"event_id": "EXT-2041", "event_date": d("2026-07-19"), "end_date": d("2026-07-21"),
     "event_title": "Consumer technology expo at Pragati Maidan",
     "event_description": "Three-day consumer electronics and technology exhibition in New Delhi.",
     "event_category": "other", "region": "Delhi NCR", "source": "City Events Listing",
     "source_url": "https://example.com/events/tech-expo", "related_sku_ids": "", "related_category": "",
     "severity": "low"},
    {"event_id": "EXT-2051", "event_date": d("2026-07-05"), "end_date": d("2026-07-09"),
     "event_title": "IMD red alert: extreme rainfall in Mumbai and Pune",
     "event_description": "Extreme rainfall and waterlogging reported across Mumbai and Pune; local transport "
                          "and retail footfall disrupted.",
     "event_category": "weather", "region": "Maharashtra", "source": "IMD Bulletin",
     "source_url": "https://example.com/imd/mh-red-alert", "related_sku_ids": "", "related_category": "",
     "severity": "high"},
]

SCENARIO_OPERATIONAL_EVENTS = [
    {"event_id": "OPS-3001", "date": d("2026-06-08"), "end_date": d("2026-06-13"), "event_type": "transport_strike",
     "region": "Telangana", "affected_facility": "DC-HYD-01",
     "description": "Truckers' association strike halts outbound dispatch from DC-HYD-01 to distributors; "
                    "shipment delays across Hyderabad and Warangal routes.",
     "related_sku_ids": "", "related_category": "", "severity": "high"},
    {"event_id": "OPS-3002", "date": d("2026-05-18"), "end_date": d("2026-05-18"), "event_type": "maintenance",
     "region": "Telangana", "affected_facility": "DC-HYD-01",
     "description": "Scheduled conveyor maintenance at DC-HYD-01 (night shift, no dispatch impact planned).",
     "related_sku_ids": "", "related_category": "", "severity": "low"},
    {"event_id": "OPS-3021", "date": d("2026-02-02"), "end_date": d("2026-02-06"), "event_type": "quality_hold",
     "region": "Tamil Nadu", "affected_facility": "PLANT-CHN-02",
     "description": "QA deviation: elevated acidity detected in curd batch B-2291; partial hold released after "
                    "re-testing. Batch distributed to Chennai and Coimbatore distributors.",
     "related_sku_ids": "SKU-401", "related_category": "Dairy", "severity": "medium"},
    {"event_id": "OPS-3031", "date": d("2026-07-06"), "end_date": d("2026-07-10"), "event_type": "facility_disruption",
     "region": "Maharashtra", "affected_facility": "DC-PUN-02",
     "description": "Waterlogging at DC-PUN-02 suspends outbound dispatch; home care replenishment to Mumbai and "
                    "Pune distributors delayed.",
     "related_sku_ids": "", "related_category": "Home Care", "severity": "high"},
]

# Generic background events (no injected effect) used to add realistic noise
BACKGROUND_EXTERNAL = [
    ("Fuel price revision announced", "macroeconomic", "National", "", "low"),
    ("State government announces revised excise duty", "regulatory", "{region}", "", "low"),
    ("Competitor launches new flavour variant", "competitor_promotion", "{region}", "{category}", "low"),
    ("Local cricket tournament final", "cultural_event", "{region}", "", "low"),
    ("Heatwave advisory issued", "weather", "{region}", "", "low"),
    ("Viral recipe video features home cooking staples", "social_trend", "National", "{category}", "low"),
    ("Retail chain opens new hypermarket", "other", "{region}", "", "low"),
    ("Monsoon onset declared", "weather", "{region}", "", "low"),
    ("FSSAI issues labelling guidance update", "regulatory", "National", "{category}", "low"),
    ("Consumer sentiment index released", "macroeconomic", "National", "", "low"),
]
BACKGROUND_OPERATIONAL = [
    ("maintenance", "Scheduled preventive maintenance at {facility}; no dispatch impact expected.", "low"),
    ("supplier_delay", "Minor packaging supplier delay at {facility}; buffer stock sufficient.", "low"),
    ("maintenance", "IT system upgrade at {facility} warehouse management system over weekend.", "low"),
]
