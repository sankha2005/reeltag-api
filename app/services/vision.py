import json
from dataclasses import dataclass
from typing import List
from app.config import settings


@dataclass
class VisionExtraction:
    canonical_title: str
    brand: str
    category: str
    estimated_insta_price: int
    search_queries: List[str]
    confidence: float


VISION_PROMPT = """You are ReelTag's product identification engine for Indian consumers.
Analyze this Instagram Reel / Story screenshot and identify the exact physical consumer product shown.
Return STRICT JSON with these keys only:
{
  "canonical_title": "Clean, accurate product name as sold on Amazon India / Myntra / Nykaa / Flipkart",
  "brand": "Original brand name (or 'Generic / Original OEM' if unbranded viral item)",
  "category": "One of: Beauty & Skincare | Fashion & Bags | Home & Lamps | Gadgets",
  "estimated_insta_price": 1499,
  "search_queries": ["primary India shopping search query", "shorter fallback query"],
  "confidence": 0.94
}
"""


VISION_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]


async def identify_product_from_screenshot(image_bytes: bytes) -> VisionExtraction:
    """
    Calls Gemini 2.5 Flash to identify the canonical product from an Instagram screenshot.
    Falls back cleanly if GEMINI_API_KEY is not configured in local dev.
    """
    if not settings.gemini_api_key:
        return VisionExtraction(
            canonical_title="Korean Glass Skin Snail 96 Mucin Power Essence (100ml)",
            brand="COSRX Official",
            category="Beauty & Skincare",
            estimated_insta_price=2199,
            search_queries=["COSRX Advanced Snail 96 Mucin Power Essence 100ml"],
            confidence=0.95,
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)

    # Gemini Flash models get overloaded (HTTP 503) or retired (404) without
    # warning, so try a short chain instead of pinning one model. The first
    # model that answers wins.
    last_error: Exception | None = None
    data = None
    for model_name in VISION_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    VISION_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text)
            break
        except Exception as exc:  # noqa: BLE001 - fall through to the next model
            last_error = exc
            continue

    if data is None:
        raise RuntimeError(
            f"All Gemini vision models failed. Last error: {last_error}"
        )

    valid_categories = {"Beauty & Skincare", "Fashion & Bags", "Home & Lamps", "Gadgets"}
    category = data.get("category", "Gadgets")
    if category not in valid_categories:
        category = "Gadgets"

    queries = data.get("search_queries") or [data.get("canonical_title", "viral product")]
    return VisionExtraction(
        canonical_title=str(data.get("canonical_title", "Trending Product")).strip(),
        brand=str(data.get("brand", "Verified Brand")).strip(),
        category=category,
        estimated_insta_price=max(299, int(data.get("estimated_insta_price", 1499))),
        search_queries=[str(q).strip() for q in queries if str(q).strip()],
        confidence=float(data.get("confidence", 0.92)),
    )
