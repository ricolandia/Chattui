"""Cliente de embeddings compartilhado (API OpenAI-compatível `/embeddings`).

Usado pelo RAG (rag.py) e pela memória semântica (memory.py) — na prática
o endpoint do Ollama servindo `nomic-embed-text` ou similar. Sem numpy:
a memória usa cosseno em Python puro; o RAG continua com a matriz mmap.
"""

from __future__ import annotations

from array import array

import httpx


class Embedder:
    def __init__(self, api_base: str, model: str, api_key: str | None = None):
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.api_key = api_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.api_base}/embeddings",
                json={"model": self.model, "input": texts},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return [d["embedding"] for d in data["data"]]


def cosine(a: list[float] | array, b: list[float] | array) -> float:
    """Similaridade de cosseno em Python puro (memória é pequena)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = norm_a = norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def to_blob(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def from_blob(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    vec = array("f")
    vec.frombytes(blob)
    return vec.tolist()
