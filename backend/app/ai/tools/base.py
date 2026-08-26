from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    Base contract for all Vibe AI tools.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def execute(
        self,
        **kwargs: Any,
    ) -> Any:
        pass

    def definition(self) -> dict[str, Any]:
        """
        Provider-independent tool definition.
        """

        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
