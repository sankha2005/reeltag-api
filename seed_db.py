"""Seed the ReelTag SQLite DB with the frontend's 6 mock catalog products.

Each offer gets a real store search URL so /api/go/{offer_id} redirects work
before SERPAPI/Cuelinks are configured (affiliate.py then adds UTM fallbacks).
Run:  .venv/Scripts/python seed_db.py
"""
import sys

from app.config import settings
from app.db import init_db, save_product
from app.models import Product, StoreOffer

STORE_SEARCH = {
    "Amazon India": lambda q: f"https://www.amazon.in/s?k={q}",
    "Myntra": lambda q: f"https://www.myntra.com/{q}",
    "Nykaa": lambda q: f"https://www.nykaa.com/search/result/?q={q}",
    "Flipkart": lambda q: f"https://www.flipkart.com/search?q={q}",
    "Meesho": lambda q: f"https://www.meesho.com/search?q={q}",
    "Tira": lambda q: f"https://www.tirabeauty.com/products/?q={q}",
}

import urllib.parse


def qs(query: str) -> str:
    return urllib.parse.quote_plus(query)


PRODUCTS = [
    {
        "id": "prod_1",
        "slug": "cosrx-advanced-snail-96-mucin-essence",
        "title": "Korean Glass Skin Snail 96 Mucin Power Essence (100ml)",
        "brand": "COSRX Official",
        "category": "Beauty & Skincare",
        "image": "/images/serum.jpg",
        "instaAdPrice": 2199,
        "lowestPrice": 889,
        "savingsAmount": 1310,
        "savingsPercent": 60,
        "checkedAgo": "1h ago",
        "instaPageHandleExample": "Boutique K-Beauty Reel Ads",
        "q": "COSRX Advanced Snail 96 Mucin Power Essence 100ml",
        "offers": [
            ("off_cosrx_myntra", "Myntra", 889, "Express 2-day delivery", "Supercom Net"),
            ("off_cosrx_nykaa", "Nykaa", 945, "100% Authentic Badge", "Nykaa E-Retail"),
            ("off_cosrx_amazon", "Amazon India", 999, "Prime Tomorrow", "RK World Infocom"),
            ("off_cosrx_tira", "Tira", 1050, "Free shipping", None),
            ("off_cosrx_flipkart", "Flipkart", 1090, "Flipkart Assured", None),
        ],
    },
    {
        "id": "prod_2",
        "slug": "viral-16-color-sunset-projection-lamp",
        "title": "180° Aluminium Sunset Projection Lamp with App & Remote",
        "brand": "Desidiya / Solimo",
        "category": "Home & Lamps",
        "image": "/images/sunset-lamp.jpg",
        "instaAdPrice": 1499,
        "lowestPrice": 299,
        "savingsAmount": 1200,
        "savingsPercent": 80,
        "checkedAgo": "2h ago",
        "instaPageHandleExample": "Aesthetic Room Decor Ads",
        "q": "16 color sunset projection lamp with remote",
        "offers": [
            ("off_lamp_amazon", "Amazon India", 299, "Prime 1-Day Delivery", None),
            ("off_lamp_flipkart", "Flipkart", 329, "Flipkart Assured", None),
            ("off_lamp_meesho", "Meesho", 345, "Free Cash on Delivery", None),
        ],
    },
    {
        "id": "prod_3",
        "slug": "minimalist-vegan-leather-slouch-tote-bag",
        "title": "Minimalist Oversized Vegan Leather Slouch Work Tote (Fits 15” Laptop)",
        "brand": "H&M / Miraggio Alt",
        "category": "Fashion & Bags",
        "image": "/images/tote-bag.jpg",
        "instaAdPrice": 2899,
        "lowestPrice": 899,
        "savingsAmount": 2000,
        "savingsPercent": 69,
        "checkedAgo": "45m ago",
        "instaPageHandleExample": "Insta Luxe Bag Dropshippers",
        "q": "oversized vegan leather slouch tote bag laptop",
        "offers": [
            ("off_tote_myntra", "Myntra", 899, "14-Day Easy Exchange", None),
            ("off_tote_amazon", "Amazon India", 979, "Prime Free Delivery", None),
            ("off_tote_flipkart", "Flipkart", 1049, "In Stock", None),
            ("off_tote_nykaa", "Nykaa", 1199, "Nykaa Fashion Verified", None),
        ],
    },
    {
        "id": "prod_4",
        "slug": "portable-inkless-mini-thermal-pocket-printer",
        "title": "Bluetooth Mini Pocket Inkless Thermal Printer + 5 Sticker Rolls",
        "brand": "PeriPage / Seznik",
        "category": "Gadgets",
        "image": "/images/thermal-printer.jpg",
        "instaAdPrice": 2499,
        "lowestPrice": 1099,
        "savingsAmount": 1400,
        "savingsPercent": 56,
        "checkedAgo": "2h ago",
        "instaPageHandleExample": "Studygram Gadget Stores",
        "q": "bluetooth mini pocket thermal printer sticker rolls",
        "offers": [
            ("off_printer_amazon", "Amazon India", 1099, "Prime + 7-Day Replacement", None),
            ("off_printer_flipkart", "Flipkart", 1149, "Open Box Delivery", None),
            ("off_printer_meesho", "Meesho", 1199, "7-Day Easy Return", None),
        ],
    },
    {
        "id": "prod_5",
        "slug": "ceramic-matcha-whisk-set-bamboo-chasen",
        "title": "Handcrafted Ceramic Spouted Matcha Bowl & 100-Prong Bamboo Chasen Set",
        "brand": "Tencha / Urban Platter",
        "category": "Home & Lamps",
        "image": "/images/matcha-set.jpg",
        "instaAdPrice": 3299,
        "lowestPrice": 1249,
        "savingsAmount": 2050,
        "savingsPercent": 62,
        "checkedAgo": "3h ago",
        "instaPageHandleExample": "Slow Living Cafe Reel Shops",
        "q": "ceramic matcha bowl bamboo chasen whisk set",
        "offers": [
            ("off_matcha_amazon", "Amazon India", 1249, "Prime Safe Packaging", None),
            ("off_matcha_flipkart", "Flipkart", 1380, "In Stock", None),
            ("off_matcha_myntra", "Myntra", 1499, "Myntra Home", None),
        ],
    },
    {
        "id": "prod_6",
        "slug": "matte-pastel-jumbo-claw-clip-6-pack",
        "title": "Soft-Touch Matte Neutral Korean Jumbo Hair Claw Clips (Pack of 6)",
        "brand": "ToniQ / Savana",
        "category": "Fashion & Bags",
        "image": "/images/claw-clips.jpg",
        "instaAdPrice": 799,
        "lowestPrice": 199,
        "savingsAmount": 600,
        "savingsPercent": 75,
        "checkedAgo": "1h ago",
        "instaPageHandleExample": "Insta Thrift & Hair Boutiques",
        "q": "matte pastel jumbo hair claw clips pack of 6",
        "offers": [
            ("off_clips_meesho", "Meesho", 199, "Free Delivery", None),
            ("off_clips_amazon", "Amazon India", 229, "Prime Tomorrow", None),
            ("off_clips_myntra", "Myntra", 249, "In Stock", None),
            ("off_clips_nykaa", "Nykaa", 279, "In Stock", None),
        ],
    },
]


def main() -> None:
    init_db()
    for p in PRODUCTS:
        query = p["q"]
        offers = [
            StoreOffer(
                offerId=oid,
                store=store,  # type: ignore[arg-type]
                price=price,
                inStock=True,
                deliveryNote=note,
                verifiedSeller=seller,
                url=STORE_SEARCH[store](qs(query)),
            )
            for oid, store, price, note, seller in p["offers"]
        ]
        product = Product(
            id=p["id"],
            slug=p["slug"],
            title=p["title"],
            brand=p["brand"],
            category=p["category"],  # type: ignore[arg-type]
            image=p["image"],
            instaAdPrice=p["instaAdPrice"],
            lowestPrice=p["lowestPrice"],
            savingsAmount=p["savingsAmount"],
            savingsPercent=p["savingsPercent"],
            checkedAgo=p["checkedAgo"],
            instaPageHandleExample=p["instaPageHandleExample"],
            offers=offers,
        )
        save_product(product)
        print(f"seeded {product.slug} ({len(offers)} offers)")

    print(f"\nDone. DB: {settings.database_path}")


if __name__ == "__main__":
    sys.exit(main())
