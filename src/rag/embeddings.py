"""
Embedding generator using LM Studio's local embedding API.
Uses text-embedding-nomic-embed-text-v1.5 (768-dim).
"""

import httpx
from config.settings import settings

EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5"
EMBEDDING_DIM = 768


def encode_text(text: str) -> list[float]:
    """Encode a single text to embedding vector via LM Studio."""
    try:
        r = httpx.post(
            f"{settings.lmstudio_base_url}/v1/embeddings",
            json={"model": EMBEDDING_MODEL, "input": text},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception:
        # Fallback: return zero vector on failure
        return [0.0] * EMBEDDING_DIM


def encode_texts(texts: list[str]) -> list[list[float]]:
    """Batch encode multiple texts."""
    return [encode_text(t) for t in texts]


def get_embedding_dim() -> int:
    return EMBEDDING_DIM
