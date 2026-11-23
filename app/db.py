import json
import sqlite3
import time
from contextlib import closing
from typing import List, Optional, Tuple
from app.config import settings
from app.models import Product, StoreOffer
from app.services.fingerprint import hamming_distance


def get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    with closing(get_conn(db_path)) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                brand TEXT NOT NULL,
                category TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS image_hashes (
                dhash TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS offers (
                offer_id TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                store TEXT NOT NULL,
                raw_url TEXT NOT NULL,
                price INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS click_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id TEXT NOT NULL,
                store TEXT NOT NULL,
                clicked_at INTEGER NOT NULL
            );
            """
        )


def save_product(product: Product, dhash: Optional[str] = None, db_path: Optional[str] = None) -> None:
    now = int(time.time())
    with closing(get_conn(db_path)) as conn, conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO products (slug, title, brand, category, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (product.slug, product.title, product.brand, product.category, product.model_dump_json(), now),
        )
        # Re-saving a product may drop offers (e.g. a store went out of stock).
        # Remove stale rows so click lookups can't resolve retired offers.
        conn.execute("DELETE FROM offers WHERE slug = ?", (product.slug,))
        for offer in product.offers:
            conn.execute(
                """
                INSERT OR REPLACE INTO offers (offer_id, slug, store, raw_url, price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (offer.offerId, product.slug, offer.store, offer.url, offer.price),
            )
        if dhash:
            conn.execute(
                "INSERT OR REPLACE INTO image_hashes (dhash, slug, created_at) VALUES (?, ?, ?)",
                (dhash, product.slug, now),
            )


def find_product_by_slug(slug: str, db_path: Optional[str] = None) -> Optional[Product]:
    with closing(get_conn(db_path)) as conn, conn:
        row = conn.execute("SELECT payload_json FROM products WHERE slug = ?", (slug,)).fetchone()
    if not row:
        return None
    return Product.model_validate_json(row["payload_json"])


def find_similar_by_dhash(target_dhash: str, max_distance: int = 8, db_path: Optional[str] = None) -> Optional[Product]:
    with closing(get_conn(db_path)) as conn, conn:
        rows = conn.execute("SELECT dhash, slug FROM image_hashes").fetchall()
    best_slug = None
    best_dist = max_distance + 1
    for row in rows:
        dist = hamming_distance(target_dhash, row["dhash"])
        if dist < best_dist:
            best_dist = dist
            best_slug = row["slug"]
    return find_product_by_slug(best_slug, db_path) if best_slug else None


def search_cached_products(query: str, category: Optional[str] = None, db_path: Optional[str] = None) -> List[Product]:
    tokens = [t.lower() for t in query.split() if t.strip()]
    with closing(get_conn(db_path)) as conn, conn:
        if category and category != "All Trending":
            rows = conn.execute("SELECT payload_json FROM products WHERE category = ?", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT payload_json FROM products").fetchall()

    scored: List[Tuple[int, Product]] = []
    for row in rows:
        p = Product.model_validate_json(row["payload_json"])
        hay = f"{p.title} {p.brand} {p.category}".lower()
        score = sum(1 for tok in tokens if tok in hay)
        if not tokens or score > 0:
            scored.append((score, p))

    scored.sort(key=lambda item: (-item[0], item[1].lowestPrice))
    return [p for _, p in scored]


def lookup_offer_and_log_click(offer_id: str, db_path: Optional[str] = None) -> Optional[Tuple[str, str]]:
    with closing(get_conn(db_path)) as conn, conn:
        row = conn.execute("SELECT store, raw_url FROM offers WHERE offer_id = ?", (offer_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            "INSERT INTO click_logs (offer_id, store, clicked_at) VALUES (?, ?, ?)",
            (offer_id, row["store"], int(time.time())),
        )
        return row["store"], row["raw_url"]
