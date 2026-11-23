from typing import List, Literal, Optional
from pydantic import BaseModel

Category = Literal[
    "Beauty & Skincare",
    "Fashion & Bags",
    "Home & Lamps",
    "Gadgets",
]

StoreName = Literal[
    "Amazon India",
    "Myntra",
    "Nykaa",
    "Flipkart",
    "Meesho",
    "Tira",
]


class StoreOffer(BaseModel):
    offerId: str
    store: StoreName
    price: int
    inStock: bool = True
    deliveryNote: str = "Verified Indian Store"
    verifiedSeller: Optional[str] = None
    url: str = ""


class Product(BaseModel):
    id: str
    slug: str
    title: str
    brand: str
    category: Category
    image: str
    instaAdPrice: int
    lowestPrice: int
    savingsAmount: int
    savingsPercent: int
    checkedAgo: str
    instaPageHandleExample: str
    offers: List[StoreOffer]


class ScanResult(BaseModel):
    matchedProduct: Product
    confidence: float
    cacheHit: bool = False
    imageHash: str = ""


class SearchResponse(BaseModel):
    query: str
    source: Literal["live", "cache"]
    results: List[Product]
