"""Registry for hardware diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from .base import HardwareTest, HardwareTestResult


@dataclass
class HardwareTestRegistry:
    """In-memory registry tracking available hardware diagnostics."""

    tests: Dict[str, HardwareTest] = field(default_factory=dict)

    def register(self, *tests: HardwareTest) -> None:
        """Register test instances with the registry."""

        for test in tests:
            self.tests[test.id] = test

    def extend(self, tests: Iterable[HardwareTest]) -> None:
        """Register multiple tests from an iterable."""

        for test in tests:
            self.register(test)

    def list_tests(self) -> List[dict]:
        """Return metadata describing available tests."""

        return [test.to_metadata() for test in self.tests.values()]

    def get_test(self, test_id: str) -> HardwareTest:
        """Return a registered test or raise KeyError."""

        try:
            return self.tests[test_id]
        except KeyError as exc:
            raise KeyError(f"No hardware test registered with id '{test_id}'") from exc

    def run_test(self, test_id: str) -> HardwareTestResult:
        """Execute a single test by id."""

        test = self.get_test(test_id)
        return test.run()

    def run_all(self) -> List[HardwareTestResult]:
        """Execute all registered tests in insertion order."""

        return [test.run() for test in self.tests.values()]
