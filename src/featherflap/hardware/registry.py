"""Registry for hardware diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from ..logger import get_logger
from .base import HardwareTest, HardwareTestResult

logger = get_logger(__name__)


@dataclass
class HardwareTestRegistry:
    """In-memory registry tracking available hardware diagnostics."""

    tests: Dict[str, HardwareTest] = field(default_factory=dict)

    def register(self, *tests: HardwareTest) -> None:
        """Register test instances with the registry."""

        for test in tests:
            if test.id in self.tests:
                logger.warning("Replacing existing hardware test registration: %s", test.id)
            self.tests[test.id] = test
            logger.debug("Registered hardware test: %s", test.id)

    def extend(self, tests: Iterable[HardwareTest]) -> None:
        """Register multiple tests from an iterable."""

        for test in tests:
            self.register(test)

    def list_tests(self) -> List[dict]:
        """Return metadata describing available tests."""

        metadata = [test.to_metadata() for test in self.tests.values()]
        logger.debug("Generated metadata for %d hardware tests", len(metadata))
        return metadata

    def get_test(self, test_id: str) -> HardwareTest:
        """Return a registered test or raise KeyError."""

        try:
            return self.tests[test_id]
        except KeyError as exc:
            logger.error("Requested unknown hardware test: %s", test_id)
            raise KeyError(f"No hardware test registered with id '{test_id}'") from exc

    def run_test(self, test_id: str) -> HardwareTestResult:
        """Execute a single test by id."""

        test = self.get_test(test_id)
        logger.info("Running hardware test: %s", test.id)
        result = test.run()
        logger.info("Hardware test '%s' completed with status %s", result.id, result.status.value)
        return result

    def run_all(self) -> List[HardwareTestResult]:
        """Execute all registered tests in insertion order."""

        logger.info("Running full hardware test suite (%d tests)", len(self.tests))
        results = [test.run() for test in self.tests.values()]
        logger.info("Completed full hardware test suite")
        return results
