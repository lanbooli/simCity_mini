"""
Embedding generator — routes to the correct provider based on config.
Defaults: LM Studio → nomic-embed-text-v1.5 / DeepSeek → configured model.
"""

import httpx
from config.settings import settings


def _get_embedding_config():
    """Resolve embedding endpoint based on provider and settings overrides."""
    provider = settings.llm_provider

    # Base URL: explicit override > provider default
    if settings.embedding_base_url:
        base_url = settings.embedding_base_url.rstrip("/")
    elif provider == "deepseek":
        base_url = settings.deepseek_base_url.rstrip("/")
    else:
        base_url = settings.lmstudio_base_url.rstrip("/")

    # Model: explicit override > provider default
    if settings.embedding_model:
        model = settings.embedding_model
    elif provider == "lmstudio":
        model = "text-embedding-nomic-embed-text-v1.5"
    else:
        model = settings.deepseek_main_model  # fallback for deepseek/other

    return base_url, model, settings.embedding_dim


def encode_text(text: str) -> list[float]:
    """Encode a single text to embedding vector."""
    base_url, model, dim = _get_embedding_config()
    try:
        r = httpx.post(
            f"{base_url}/v1/embeddings",
            json={"model": model, "input": text},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception:
        return [0.0] * dim


def encode_texts(texts: list[str]) -> list[list[float]]:
    """Batch encode multiple texts."""
    return [encode_text(t) for t in texts]


def get_embedding_dim() -> int:
    return settings.embedding_dim
