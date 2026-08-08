from hashlib import sha256


class PromptCache:
    def __init__(self):
        self._cache: dict[str, str] = {}

    def _key(self, prompt: str) -> str:
        return sha256(prompt.encode()).hexdigest()

    def get(self, prompt: str) -> str | None:
        key = self._key(prompt)
        return self._cache.get(key)

    def set(
        self,
        prompt: str,
        response: str,
    ) -> None:
        key = self._key(prompt)
        self._cache[key] = response

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict:
        return {
            "cached_prompts": len(self._cache),
        }