"""Base skill interface for DocAgent."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """All DocAgent skills inherit from this base class.

    Every skill:
    - takes structured input
    - returns structured output
    - is reusable and composable
    """

    name: str = "base"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"docagent.skill.{self.name}")

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the skill and return structured output."""
        ...

    def __repr__(self) -> str:
        return f"<Skill: {self.name}>"
