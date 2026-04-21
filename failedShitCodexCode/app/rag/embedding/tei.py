from __future__ import annotations

import httpx


class TEIEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        dimension: int,
        batch_size: int = 32,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = max(1, batch_size)
        self.api_key = api_key
        self.timeout = timeout

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = httpx.post(
                f"{self.base_url}/v1/embeddings",
                headers=headers,
                json={
                    "model": self.model_name,
                    "input": batch,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            batch_vectors = [item["embedding"] for item in payload.get("data", [])]
            vectors.extend(list(vector) for vector in batch_vectors)
        return vectors
