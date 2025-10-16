"""Base classes and utilities for hardware diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from ..logger import get_logger

logger = get_logger(__name__)


class HardwareStatus(str, Enum):
    """Standard result categories used throughout diagnostics."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(slots=True)
class HardwareTestResult:
    """Result returned by hardware diagnostics."""

    id: str
    name: str
    status: HardwareStatus
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of the result."""

        payload = {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "summary": self.summary,
            "details": self.details,
        }
        logger.debug("Serialised HardwareTestResult: %s", payload)
        return payload


class HardwareTest:
    """Base class for all hardware diagnostics."""

    id: str = "base"
    name: str = "Unnamed Test"
    description: str = "No description provided."
    category: str = "general"

    def run(self) -> HardwareTestResult:
        """Execute the hardware check and return a structured result."""

        raise NotImplementedError

    def to_metadata(self) -> Dict[str, Optional[str]]:
        """Return metadata describing the test."""

        metadata = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
        }
        logger.debug("Serialised HardwareTest metadata: %s", metadata)
        return metadata
