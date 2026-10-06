from __future__ import annotations

import openai

from memlite.embeddings.base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI implementation of the EmbeddingProvider protocol."""

    def __init__(
        self,
        client: openai.Client | None = None,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
    ) -> None:
        self.client = client or openai.Client()
        self._model = model
        self._dimension = dimension

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self.client.embeddings.create(
            input=texts,
            model=self._model,
        )

        return [data.embedding for data in response.data]
