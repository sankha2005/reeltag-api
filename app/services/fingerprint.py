import io
from PIL import Image


def compute_dhash(image_bytes: bytes, hash_size: int = 8) -> str:
    """
    Computes a 64-bit difference hash (dHash) from image bytes.
    Fast, zero-ML perceptual fingerprint for instant repeat-Reel cache hits.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())

    bits = []
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            bits.append(1 if pixels[row_start + col] > pixels[row_start + col + 1] else 0)

    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{value:016x}"


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Returns bitwise Hamming distance between two hex dHash strings."""
    if len(hash_a) != len(hash_b):
        return 64
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")
