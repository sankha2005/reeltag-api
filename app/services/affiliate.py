from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from app.config import settings


def wrap_affiliate_url(raw_url: str, store: str, offer_id: str) -> str:
    """
    Wraps a verified Indian store URL with Amazon India Associates `tag=`
    or Cuelinks deep-linking (`pub_id` + `subid`) for clean revenue attribution.
    """
    if not raw_url:
        return "https://reeltag.in"

    parsed = urlparse(raw_url)
    host = (parsed.netloc or "").lower()

    # 1. Amazon India Associates Program
    if "amazon.in" in host or store == "Amazon India":
        qs = parse_qs(parsed.query)
        qs["tag"] = [settings.amazon_associate_tag or "reeltag-21"]
        qs["ascsubtag"] = [offer_id]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    # 2. Cuelinks wrapper (Myntra, Nykaa, Flipkart, Meesho, Tira)
    if settings.cuelinks_pub_id:
        params = urlencode(
            {
                "id": settings.cuelinks_pub_id,
                "url": raw_url,
                "subid": offer_id,
            }
        )
        return f"https://linksredirect.com/?{params}"

    # 3. Clean UTM fallback when affiliate IDs are not yet configured
    qs = parse_qs(parsed.query)
    qs["utm_source"] = ["reeltag.in"]
    qs["utm_medium"] = ["price_compare"]
    qs["utm_campaign"] = [offer_id]
    return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))
