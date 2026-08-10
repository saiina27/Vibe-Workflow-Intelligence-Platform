
from math import ceil


class TextChunker:

    def __init__(
        self,
        chunk_size: int = 1000,
        overlap: int = 200,
    ):
        if chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than 0."
            )

        if overlap < 0:
            raise ValueError(
                "overlap cannot be negative."
            )

        if overlap >= chunk_size:
            raise ValueError(
                "overlap must be smaller than chunk_size."
            )

        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(
        self,
        text: str,
    ) -> list[str]:

        if not text or not text.strip():
            return []

        text = text.strip()

        chunks = []

        step = (
            self.chunk_size
            - self.overlap
        )

        start = 0

        while start < len(text):

            end = start + self.chunk_size

            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            start += step

        return chunks

    def estimate_chunks(
        self,
        text: str,
    ) -> int:

        if not text or not text.strip():
            return 0

        step = (
            self.chunk_size
            - self.overlap
        )

        return ceil(
            len(text) / step
        )

