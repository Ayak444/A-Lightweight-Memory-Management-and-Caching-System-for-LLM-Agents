from __future__ import annotations

import math
import re
from hashlib import blake2b

from memlite.models import normalize_content

_LATIN_TOKEN = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")


class DeterministicHashEmbedding:
    """A dependency-free lexical embedding for tests and offline baselines."""

    def __init__(self, dimension: int = 256) -> None:
        if dimension < 32:
            raise ValueError("dimension must be at least 32")
        self._dimension = dimension

    @property
    def model_id(self) -> str:
        return f"deterministic-hash-v1-{self.dimension}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("text must not be empty")

        vector = [0.0] * self.dimension
        for feature in self._features(text):
            digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            raise ValueError("text produced no embedding features")
        return [value / magnitude for value in vector]

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = normalize_content(text)
        latin = _LATIN_TOKEN.findall(normalized)
        cjk = [character for character in normalized if "\u3400" <= character <= "\u9fff"]
        cjk_bigrams = ["".join(cjk[index : index + 2]) for index in range(len(cjk) - 1)]
        latin_bigrams = ["::".join(latin[index : index + 2]) for index in range(len(latin) - 1)]
        return latin + latin_bigrams + cjk + cjk_bigrams
