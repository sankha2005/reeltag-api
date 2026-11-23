import io
import os
import tempfile
from PIL import Image

from app.services.fingerprint import compute_dhash, hamming_distance
from app.services.shopping import (
    build_product_from_shopping_items,
    is_relevant_title,
    normalize_trusted_store,
    parse_inr_price,
    title_relevance,
)
from app.services.affiliate import wrap_affiliate_url
from app.db import init_db, save_product, find_similar_by_dhash, lookup_offer_and_log_click


def make_test_image(color):
    buf = io.BytesIO()
    im = Image.new("RGB", (200, 200), color)
    for x in range(100, 200):
        for y in range(200):
            im.putpixel((x, y), (255, 255, 255))
    im.save(buf, format="JPEG")
    return buf.getvalue()


def test_all():
    # 1. Perceptual dHash test
    h1 = compute_dhash(make_test_image((20, 30, 80)))
    h2 = compute_dhash(make_test_image((22, 32, 82)))
    assert len(h1) == 16
    assert hamming_distance(h1, h2) <= 2, f"Expected near-zero distance, got {hamming_distance(h1, h2)}"

    # 2. INR price parsing & trusted store filtering
    assert parse_inr_price("₹1,249.00") == 1249
    assert parse_inr_price("Rs. 889") == 889
    assert normalize_trusted_store("Amazon.in") == "Amazon India"
    assert normalize_trusted_store("Myntra") == "Myntra"
    assert normalize_trusted_store("Random Dropshipper Shop") is None

    # 3. Relevance guard: loosely related Google Shopping hits must be rejected
    assert title_relevance("sunset projection lamp", "Sunset Projection Lamp with Remote") >= 0.6
    assert (
        title_relevance(
            "sunset projection lamp",
            "1ST TIME Brown Glass Cylinder Table Lamps(Onesize) by Myntra",
        )
        < 0.6
    )
    irrelevant = [
        {
            "source": "Myntra",
            "price": "₹319",
            "link": "https://www.myntra.com/table-lamp",
            "title": "Brown Glass Cylinder Table Lamp",
        }
    ]
    assert build_product_from_shopping_items("sunset projection lamp", irrelevant) is None
    assert not is_relevant_title(
        "sunset projection lamp", "Brown Glass Cylinder Table Lamp"
    )
    assert is_relevant_title(
        "COSRX Advanced Snail 96 Mucin Power Essence 100ml",
        "COSRX Advanced Snail 96 Mucin Essence (100 ml)",
    )
    assert not is_relevant_title(
        "COSRX Advanced Snail 96 Mucin Power Essence 100ml",
        "COSRX Advanced Snail Radiance Dual Essence",
    )
    assert not is_relevant_title(
        "COSRX Advanced Snail 96 Mucin Power Essence 100ml",
        "COSRX Advanced Snail 96 Mucin Power Essence 100ml + Azzaro Perfume Combo",
    )
    assert not is_relevant_title(
        "COSRX Snail Mucin", "Cosrx Snail Mucin Glow Kit Australia"
    )

    # 3c. Cross-store offers must describe one product family, not four listings
    families = [
        {"source": "Amazon.in", "price": "₹999", "link": "https://www.amazon.in/dp/A", "title": "COSRX Snail 96 Mucin Essence 100ml"},
        {"source": "Nykaa", "price": "₹945", "link": "https://www.nykaa.com/a", "title": "COSRX Snail 96 Mucin Essence"},
        {"source": "Myntra", "price": "₹889", "link": "https://www.myntra.com/a", "title": "COSRX Snail 96 Mucin Essence 100 ml"},
        {"source": "Flipkart", "price": "₹449", "link": "https://www.flipkart.com/b", "title": "COSRX Snail Mucin 92 Repair Cream"},
        {"source": "Meesho", "price": "₹399", "link": "https://www.meesho.com/b", "title": "COSRX Snail Mucin Repair Cream"},
    ]
    mixed = build_product_from_shopping_items("COSRX Snail Mucin", families)
    assert mixed is not None
    assert {offer.store for offer in mixed.offers} == {
        "Amazon India",
        "Nykaa",
        "Myntra",
    }

    # 3b. Brand guard: lookalike listings must not masquerade as the original
    lookalike = [
        {
            "source": "Flipkart",
            "price": "₹445",
            "link": "https://www.flipkart.com/sx-next-snail",
            "title": "Sx Next Advanced Snail 96 Mucin Power Essence",
        }
    ]
    assert (
        build_product_from_shopping_items(
            "COSRX Advanced Snail 96 Mucin Power Essence", lookalike, brand="COSRX"
        )
        is None
    )
    genuine = [
        {
            "source": "Amazon.in",
            "price": "₹999",
            "link": "https://www.amazon.in/dp/B00PBX3L7K",
            "title": "COSRX Advanced Snail 96 Mucin Power Essence 100ml",
        }
    ]
    assert (
        build_product_from_shopping_items(
            "COSRX Advanced Snail 96 Mucin Power Essence", genuine, brand="COSRX"
        )
        is not None
    )
    # The search endpoint uses the placeholder brand "Verified Original"; it must
    # not be treated as a real brand to enforce in titles.
    assert (
        build_product_from_shopping_items(
            "COSRX Snail 96 Mucin",
            [
                {
                    "source": "Amazon.in",
                    "price": "₹999",
                    "link": "https://www.amazon.in/dp/B00PBX3L7K",
                    "title": "COSRX Snail 96 Mucin Essence",
                }
            ],
        )
        is not None
    )

    # 4. Deduplication & strict lowest-price-first sorting
    raw = [
        {"source": "Flipkart", "price": "₹1,090", "link": "https://www.flipkart.com/cosrx", "title": "COSRX Snail 96 Mucin Essence"},
        {"source": "Myntra", "price": "₹949", "link": "https://www.myntra.com/cosrx-alt", "title": "COSRX Snail 96 Mucin Essence 100ml"},
        {"source": "Myntra", "price": "₹889", "link": "https://www.myntra.com/cosrx-best", "title": "COSRX Advanced Snail 96 Mucin Power Essence"},
        {"source": "ShadyInstaStore", "price": "₹199", "link": "https://shady.shop/fake", "title": "COSRX Snail 96 Mucin Essence"},
        {"source": "Amazon.in", "price": "₹999", "link": "https://www.amazon.in/dp/B00PBX3L7K", "title": "COSRX Snail 96 Mucin Essence"},
    ]
    prod = build_product_from_shopping_items("COSRX Snail 96 Mucin", raw, category="Beauty & Skincare", brand="COSRX", insta_ad_price_override=2199)
    assert prod is not None
    assert len(prod.offers) == 3  # ShadyInstaStore excluded, Myntra deduplicated
    assert prod.offers[0].store == "Myntra" and prod.offers[0].price == 889
    assert prod.lowestPrice == 889
    assert prod.savingsAmount == 1310

    # 5. Affiliate URL wrapping
    amz = wrap_affiliate_url("https://www.amazon.in/dp/B00PBX3L7K", "Amazon India", prod.offers[1].offerId)
    assert "tag=" in amz and "ascsubtag=" in amz

    # 6. SQLite persistence + dHash cache hit + click log
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    try:
        init_db(db_path)
        save_product(prod, dhash=h1, db_path=db_path)
        cached = find_similar_by_dhash(h2, db_path=db_path)
        assert cached is not None and cached.slug == prod.slug
        offer_hit = lookup_offer_and_log_click(prod.offers[0].offerId, db_path=db_path)
        assert offer_hit is not None and offer_hit[0] == "Myntra"
    finally:
        os.remove(db_path)

    print("ALL ENGINE TESTS PASSED!")


if __name__ == "__main__":
    test_all()
