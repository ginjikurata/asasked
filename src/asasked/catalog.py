"""A product catalog with attributes that Verifiable Intent constraints lack.

The standard checks a purchase by sku, amount and merchant. Everything else
(product level, returnability, delivery time, colour, size) takes no part in
the check. These fields are here to show exactly what gets lost.
"""

MERCHANTS = [
    {"id": "m-1", "name": "Tennis Warehouse", "website": "https://tennis-warehouse.com"},
    {"id": "m-2", "name": "Racket Outlet", "website": "https://racket-outlet.example"},
]

PRODUCTS = [
    # ---- rackets -------------------------------------------------------
    {
        "sku": "BAB-PA-98", "name": "Babolat Pure Aero 98",
        "brand": "Babolat", "category": "racket", "level": "pro",
        "price_cents": 39900, "color": "yellow", "size_label": "4 3/8",
        "refundable": False, "ships_in_days": 2, "pack_size": 1,
    },
    {
        "sku": "BAB-DR-JR", "name": "Babolat Drive Junior",
        "brand": "Babolat", "category": "racket", "level": "beginner",
        "price_cents": 11900, "color": "blue", "size_label": "4 1/4",
        "refundable": True, "ships_in_days": 3, "pack_size": 1,
    },
    {
        "sku": "HEA-SP-PRO", "name": "HEAD Speed Pro",
        "brand": "HEAD", "category": "racket", "level": "pro",
        "price_cents": 36500, "color": "black", "size_label": "4 3/8",
        "refundable": True, "ships_in_days": 21, "pack_size": 1,
    },
    {
        "sku": "HEA-TI-S6", "name": "HEAD Ti.S6",
        "brand": "HEAD", "category": "racket", "level": "beginner",
        "price_cents": 9900, "color": "silver", "size_label": "4 3/8",
        "refundable": True, "ships_in_days": 2, "pack_size": 1,
    },
    # ---- balls ---------------------------------------------------------
    {
        "sku": "WIL-US-3", "name": "Wilson US Open, банка 3 мяча",
        "brand": "Wilson", "category": "balls", "level": "any",
        "price_cents": 1200, "color": "yellow", "size_label": "",
        "refundable": True, "ships_in_days": 2, "pack_size": 3,
    },
    # ---- shoes ---------------------------------------------------------
    {
        "sku": "ASI-GEL-42-BK", "name": "ASICS Gel-Resolution, 42, чёрные",
        "brand": "ASICS", "category": "shoes", "level": "any",
        "price_cents": 13500, "color": "black", "size_label": "42",
        "refundable": True, "ships_in_days": 4, "pack_size": 1,
    },
    {
        "sku": "ASI-GEL-44-WH", "name": "ASICS Gel-Resolution, 44, белые",
        "brand": "ASICS", "category": "shoes", "level": "any",
        "price_cents": 13500, "color": "white", "size_label": "44",
        "refundable": True, "ships_in_days": 4, "pack_size": 1,
    },
]

BY_SKU = {p["sku"]: p for p in PRODUCTS}


def find(sku: str) -> dict:
    if sku not in BY_SKU:
        raise KeyError(f"No product {sku}")
    return BY_SKU[sku]
