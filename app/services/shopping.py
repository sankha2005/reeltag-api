import hashlib
import re
from typing import Dict, List, Optional, Tuple
import httpx
from app.config import settings
from app.models import Product, StoreOffer

TRUSTED_STORES: List[Tuple[str, str]] = [
    ("amazon", "Amazon India"),
    ("myntra", "Myntra"),
    ("nykaa", "Nykaa"),
    ("flipkart", "Flipkart"),
    ("meesho", "Meesho"),
    ("tira", "Tira"),
]

# Google Shopping returns loosely related products for broad queries (e.g. a
# table lamp for "sunset projection lamp"). Only keep hits that share enough of
# the query's meaningful words with their title, otherwise we would show a
# comparison page for the wrong product.
MIN_TITLE_RELEVANCE = 0.6

_BUNDLE_MARKERS = ("combo", "bundle", "kit", "2 in 1", "2-in-1", "free gift")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "of", "in", "on", "to",
    "by", "from", "at", "as", "is", "it",
}

_BRAND_NOISE = {
    "official", "india", "store", "stores", "brand", "original", "oem",
    "generic", "unbranded", "unknown", "care", "beauty", "verified",
    "trending", "viral", "seller", "genuine", "product", "products",
}


def _enforceable_brand_token(brand: str) -> Optional[str]:
    """
    Returns a single distinctive brand token to require in result titles.

    Only unambiguous brands (e.g. "COSRX", "Nykaa") are enforced; multi-word or
    placeholder brands ("Generic / Original OEM", "H&M / Miraggio Alt") are not,
    because rejecting on partial brand text would drop legitimate offers.
    """
    tokens = [
        _stem(token)
        for token in _tokens(brand)
        if len(token) >= 4 and token not in _STOPWORDS and token not in _BRAND_NOISE
    ]
    return tokens[0] if len(tokens) == 1 else None


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _stem(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _token_matches(needle: str, haystack: set) -> bool:
    if needle in haystack:
        return True
    if len(needle) < 4:
        return False
    return any(
        len(token) >= 4 and (token.startswith(needle) or needle.startswith(token))
        for token in haystack
    )


def _query_tokens(query: str) -> List[str]:
    return [
        _stem(token)
        for token in _tokens(query)
        if len(token) >= 2 and token not in _STOPWORDS
    ]


def title_relevance(query: str, title: str) -> float:
    """Share of the query's meaningful tokens present in a shopping result title."""
    query_tokens = _query_tokens(query)
    if not query_tokens:
        return 0.0
    title_tokens = {_stem(token) for token in _tokens(title)}
    hits = sum(1 for token in query_tokens if _token_matches(token, title_tokens))
    return hits / len(query_tokens)


def is_relevant_title(query: str, title: str) -> bool:
    """
    Long product names rarely survive verbatim, so require at least two matching
    informative tokens (one for single-token queries) covering most of the query.
    A generic "table lamp" hit for "sunset projection lamp" matches only one of
    three tokens and is rejected. Combo/bundle listings are rejected too: they
    are a different (usually pricier) SKU, not a store offer for this product.
    """
    lowered_query = query.lower()
    lowered_title = title.lower()
    if any(
        re.search(rf"\b{re.escape(marker)}\b", lowered_title)
        and not re.search(rf"\b{re.escape(marker)}\b", lowered_query)
        for marker in _BUNDLE_MARKERS
    ):
        return False

    query_tokens = _query_tokens(query)
    if not query_tokens:
        return False
    title_tokens = {_stem(token) for token in _tokens(title)}
    hits = sum(1 for token in query_tokens if _token_matches(token, title_tokens))
    required_hits = min(2, len(query_tokens))
    return hits >= required_hits and hits / len(query_tokens) >= MIN_TITLE_RELEVANCE


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:72] or "product"


def parse_inr_price(raw_price: object) -> Optional[int]:
    """Parses strings like '₹1,249.00', 'Rs. 889', or numeric values into integer INR."""
    if raw_price is None:
        return None
    if isinstance(raw_price, (int, float)):
        val = int(round(raw_price))
        return val if val > 0 else None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", str(raw_price))
    if not m:
        return None
    try:
        val = int(round(float(m.group(1).replace(",", ""))))
        return val if val > 0 else None
    except ValueError:
        return None


def normalize_trusted_store(source_name: str, link: str = "") -> Optional[str]:
    """Maps raw merchant names/domains strictly onto ReelTag's 6 trusted Indian stores."""
    haystack = f"{source_name} {link}".lower()
    for token, canonical in TRUSTED_STORES:
        if token in haystack:
            return canonical
    return None


def make_offer_id(slug: str, store: str) -> str:
    digest = hashlib.sha1(f"{slug}:{store}".encode("utf-8")).hexdigest()[:10]
    return f"off_{digest}"


def _title_token_set(title: str) -> set:
    return {
        _stem(token)
        for token in _tokens(title)
        if len(token) >= 2 and token not in _STOPWORDS
    }


def _jaccard(left: set, right: set) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cluster_by_title(
    scored_items: List[Tuple[float, dict]], threshold: float = 0.55
) -> List[dict]:
    """
    Groups shopping hits that describe the same product. Without this, the
    cheapest item per store could be four different products, which is not a
    price comparison. Single-link clustering is good enough for store titles.
    """
    clusters: List[dict] = []
    for score, item in scored_items:
        tokens = _title_token_set(str(item.get("title") or ""))
        best_cluster = None
        best_similarity = 0.0
        for cluster in clusters:
            similarity = _jaccard(tokens, cluster["tokens"])
            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster = cluster
        if best_cluster is not None and best_similarity >= threshold:
            best_cluster["items"].append((score, item))
            best_cluster["tokens"] |= tokens
        else:
            clusters.append({"items": [(score, item)], "tokens": tokens})
    return clusters


def _cluster_rank(cluster: dict) -> Tuple[int, float, int]:
    """Prefer families with the most trusted stores, then closest match, then terse title."""
    stores = set()
    for _, item in cluster["items"]:
        link = str(item.get("link") or item.get("product_link") or "")
        store = normalize_trusted_store(str(item.get("source", "")), link)
        if store:
            stores.add(store)
    average_score = sum(score for score, _ in cluster["items"]) / len(cluster["items"])
    shortest_title = min(len(str(item.get("title") or "")) for _, item in cluster["items"])
    return (len(stores), average_score, -shortest_title)


def build_product_from_shopping_items(
    query: str,
    raw_items: List[dict],
    category: str = "Gadgets",
    brand: str = "Verified Original",
    insta_ad_price_override: Optional[int] = None,
) -> Optional[Product]:
    """
    Filters raw shopping hits to trusted Indian marketplaces, drops results whose
    titles do not actually match the query, deduplicates by keeping the lowest
    verified price per store, and computes savings vs typical Insta ad price.
    """
    relevant: List[Tuple[float, dict]] = []
    brand_token = _enforceable_brand_token(brand)
    for item in raw_items:
        title = str(item.get("title") or "")
        if not is_relevant_title(query, title):
            continue
        score = title_relevance(query, title)
        if brand_token:
            title_tokens = {_stem(token) for token in _tokens(title)}
            if not _token_matches(brand_token, title_tokens):
                continue
        relevant.append((score, item))

    if not relevant:
        return None

    # Keep only one product family: offers across stores must describe the same item.
    best_cluster = max(_cluster_by_title(relevant), key=_cluster_rank)
    cluster_items = best_cluster["items"]

    best_score = max(score for score, _ in cluster_items)
    best_candidates = [item for score, item in cluster_items if score == best_score]
    # Prefer the tersest title: it is the closest to the canonical product name.
    best_item = min(
        best_candidates, key=lambda item: len(str(item.get("title") or ""))
    )

    best_by_store: Dict[str, StoreOffer] = {}
    canonical_title = str(best_item.get("title") or query).strip()
    thumbnail = str(best_item.get("thumbnail") or "")

    slug = slugify(query)

    for _, item in cluster_items:
        source = str(item.get("source", ""))
        link = str(item.get("link") or item.get("product_link") or "")
        store = normalize_trusted_store(source, link)
        if not store:
            continue

        price = parse_inr_price(item.get("extracted_price") or item.get("price"))
        if not price or price < 49:
            continue

        if not thumbnail and item.get("thumbnail"):
            thumbnail = str(item["thumbnail"])

        existing = best_by_store.get(store)
        if existing is None or price < existing.price:
            delivery = str(item.get("delivery") or "Verified Indian Store")
            best_by_store[store] = StoreOffer(
                offerId=make_offer_id(slug, store),
                store=store,  # type: ignore[arg-type]
                price=price,
                inStock=True,
                deliveryNote=delivery,
                url=link,
            )

    if not best_by_store:
        return None

    sorted_offers = sorted(best_by_store.values(), key=lambda o: o.price)
    lowest = sorted_offers[0].price
    # Typical Instagram dropshipper markup is ~2.2x-2.6x if not explicitly extracted
    insta_price = insta_ad_price_override or max(int(round(lowest * 2.3 / 100) * 100) - 1, lowest + 300)
    if insta_price <= lowest:
        insta_price = lowest + 300

    savings_amt = insta_price - lowest
    savings_pct = round((savings_amt / insta_price) * 100)

    return Product(
        id=f"prod_{hashlib.sha1(slug.encode()).hexdigest()[:8]}",
        slug=slug,
        title=canonical_title,
        brand=brand,
        category=category,  # type: ignore[arg-type]
        image=thumbnail or "/images/serum.jpg",
        instaAdPrice=insta_price,
        lowestPrice=lowest,
        savingsAmount=savings_amt,
        savingsPercent=savings_pct,
        checkedAgo="Just now",
        instaPageHandleExample="Trending Insta Reel Ads",
        offers=sorted_offers,
    )


async def search_indian_marketplaces(
    query: str,
    category: str = "Gadgets",
    brand: str = "Verified Original",
    insta_ad_price: Optional[int] = None,
) -> Optional[Product]:
    """
    Queries Google Shopping India (gl=in, hl=en) via SerpAPI for live INR prices
    across Amazon India, Myntra, Nykaa, Flipkart, Meesho, and Tira.
    """
    if not settings.serpapi_key:
        return None

    params = {
        "engine": "google_shopping",
        "q": query,
        "gl": "in",
        "hl": "en",
        "currency": "INR",
        "num": 25,
        "api_key": settings.serpapi_key,
    }

    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get("https://serpapi.com/search.json", params=params)
        resp.raise_for_status()
        payload = resp.json()

    shopping_results = payload.get("shopping_results") or []
    return build_product_from_shopping_items(
        query=query,
        raw_items=shopping_results,
        category=category,
        brand=brand,
        insta_ad_price_override=insta_ad_price,
    )
