"""Shared helpers for parsing command-line arguments in manual scripts."""

from __future__ import annotations

import argparse
from typing import Iterable, List


def parse_int_sequence(values: Iterable[str], value_name: str) -> List[int]:
    """Parse integers from CLI arguments, accepting decimal or hexadecimal input."""

    parsed: List[int] = []
    for raw in values:
        try:
            parsed.append(int(raw, 0))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid {value_name}: {raw}") from exc
    return parsed
