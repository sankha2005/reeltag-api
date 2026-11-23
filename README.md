# ReelTag Search & Visual Matching Engine (FastAPI)

Production-ready backend powering **ReelTag** (`reeltag.in`):

1. **Perceptual Fingerprint Cache (`app/services/fingerprint.py`)**: Computes a 64-bit dHash on uploaded Reel screenshots so repeat screenshots of the same viral Reel return instant cached results at zero AI/API cost.
2. **Multimodal Product Identifier (`app/services/vision.py`)**: Uses **Gemini 2.5 Flash** (`google-genai`) to extract the canonical product name, original brand, category, and estimated Instagram ad price from any screenshot.
3. **Live Indian Marketplace Aggregator (`app/services/shopping.py`)**: Queries **Google Shopping India** (`gl=in`) via SerpAPI, filters strictly to trusted Indian stores (`Amazon India`, `Myntra`, `Nykaa`, `Flipkart`, `Meesho`, `Tira`), normalizes INR pricing, deduplicates per store, and sorts lowest price first.
4. **Affiliate Redirect & Click Logger (`app/services/affiliate.py`)**: Wraps outbound `/api/go/{offer_id}` URLs with your **Amazon India Associates** `tag=` or **Cuelinks** `pub_id` + `subid` and logs clicks in SQLite.

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your GEMINI_API_KEY and SERPAPI_KEY to .env
uvicorn app.main:app --reload --port 8000
```

Then in your Next.js frontend `.env.local`:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Endpoints
- `POST /api/scan` — Upload compressed `<=800px` JPEG screenshot (`screenshot` form field)
- `GET /api/products?category=<optional>&limit=<optional>` — Cached catalog for the home feed
- `GET /api/search?q=<query>&category=<optional>` — Live keyword search across Indian marketplaces + local cache
- `GET /api/products/{slug}` — Fetch canonical product & ranked store offers
- `GET /api/go/{offer_id}` — Log click & 302 redirect to affiliate-tagged merchant URL
- `GET /health` — Service & provider configuration status

## Tests

```bash
python -m tests.test_engine
```

Run it as a module (`-m`) so the `app` package is importable from the project root.
It exercises dHash matching, INR parsing, trusted-store filtering, dedupe,
affiliate wrapping, and SQLite cache/click logging — no network keys required.
