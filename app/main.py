from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import settings
from app.catalog import seed_catalog
from app.db import (
    find_product_by_slug,
    find_similar_by_dhash,
    init_db,
    lookup_offer_and_log_click,
    save_product,
    search_cached_products,
)
from app.models import Product, ScanResult, SearchResponse
from app.services.affiliate import wrap_affiliate_url
from app.services.fingerprint import compute_dhash
from app.services.shopping import search_indian_marketplaces
from app.services.vision import identify_product_from_screenshot

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Render (and any ephemeral host) starts with an empty disk, so the schema
    # and bundled catalog are recreated on every cold start. save_product is an
    # upsert, so this is safe to run repeatedly.
    seeded = seed_catalog()
    print(f"[startup] database ready, seeded {seeded} products")
    yield


app = FastAPI(
    title="ReelTag Search & Visual Matching Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "vision_configured": bool(settings.gemini_api_key),
        "shopping_configured": bool(settings.serpapi_key),
        "amazon_tag": settings.amazon_associate_tag,
        "cuelinks_configured": bool(settings.cuelinks_pub_id),
    }


@app.post("/api/scan", response_model=ScanResult)
async def scan_screenshot(screenshot: UploadFile = File(...)) -> ScanResult:
    image_bytes = await screenshot.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty screenshot upload")

    dhash = compute_dhash(image_bytes)

    # 1. Instant perceptual cache hit (saves Vision + Shopping API costs)
    cached = find_similar_by_dhash(dhash)
    if cached:
        return ScanResult(matchedProduct=cached, confidence=0.99, cacheHit=True, imageHash=dhash)

    # 2. Identify canonical product via Gemini Vision
    vision = await identify_product_from_screenshot(image_bytes)

    # 3. Fetch live INR prices across trusted Indian stores
    live_product = None
    for q in vision.search_queries:
        live_product = await search_indian_marketplaces(
            query=q,
            category=vision.category,
            brand=vision.brand,
            insta_ad_price=vision.estimated_insta_price,
        )
        if live_product:
            break

    if not live_product:
        # Fallback to best cached match if SERPAPI_KEY is not configured yet
        cached_hits = search_cached_products(vision.canonical_title)
        if cached_hits:
            # Remember this screenshot so repeat scans are instant and free.
            save_product(cached_hits[0], dhash=dhash)
            return ScanResult(
                matchedProduct=cached_hits[0],
                confidence=vision.confidence,
                cacheHit=True,
                imageHash=dhash,
            )
        raise HTTPException(
            status_code=503,
            detail="Live shopping provider not configured. Set SERPAPI_KEY in .env to fetch live Indian store prices.",
        )

    save_product(live_product, dhash=dhash)
    return ScanResult(
        matchedProduct=live_product,
        confidence=vision.confidence,
        cacheHit=False,
        imageHash=dhash,
    )


@app.get("/api/search", response_model=SearchResponse)
async def search_products(
    q: str = Query(..., min_length=2, description="Product name, brand, or Reel keyword"),
    category: Optional[str] = Query(None),
) -> SearchResponse:
    # 1. Check live Indian marketplaces when SERPAPI_KEY is set
    live_product = await search_indian_marketplaces(query=q, category=category or "Gadgets")
    if live_product:
        save_product(live_product)
        cached = [p for p in search_cached_products(q, category) if p.slug != live_product.slug]
        return SearchResponse(query=q, source="live", results=[live_product, *cached[:7]])

    # 2. Otherwise search local SQLite catalog
    cached = search_cached_products(q, category)
    return SearchResponse(query=q, source="cache", results=cached)


@app.get("/api/products", response_model=list[Product])
def list_products(
    category: Optional[str] = Query(None),
    limit: int = Query(48, ge=1, le=200),
) -> list[Product]:
    """Curated catalog for the home feed (cached rows, cheapest first)."""
    return search_cached_products("", category)[:limit]


@app.get("/api/products/{slug}", response_model=Product)
def get_product(slug: str) -> Product:
    product = find_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.offers = sorted(product.offers, key=lambda o: o.price)
    return product


@app.get("/api/go/{offer_id}")
def redirect_offer(offer_id: str) -> RedirectResponse:
    found = lookup_offer_and_log_click(offer_id)
    if not found:
        return RedirectResponse(url="https://reeltag.in", status_code=302)
    store, raw_url = found
    affiliate_url = wrap_affiliate_url(raw_url, store, offer_id)
    return RedirectResponse(url=affiliate_url, status_code=302)
