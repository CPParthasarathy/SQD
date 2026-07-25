#!/usr/bin/env python3
"""Run the B4.1 host-side CI tooling tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


def main() -> int:
    """Discover and execute all controlled host tests."""

    repo_root = Path(__file__).resolve().parents[2]
    tests_directory = Path(__file__).resolve().parent / "tests"

    if not tests_directory.is_dir():
        print(
            f"ERROR: Host-test directory does not exist: {tests_directory}",
            file=sys.stderr,
        )
        return 2

    print("B4.1 host tests")
    print(f"Repository: {repo_root}")
    print(f"Tests:      {tests_directory}")
    print("")

    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(tests_directory),
        pattern="test_*.py",
    )

    runner = unittest.TextTestRunner(
        stream=sys.stdout,
        verbosity=2,
    )

    result = runner.run(suite)

    if result.testsRun == 0:
        print(
            "\nERROR: No B4.1 host tests were discovered.",
            file=sys.stderr,
        )
        return 2

    if not result.wasSuccessful():
        print(
            "\nFAIL: B4.1 host tests reported failures.",
            file=sys.stderr,
        )
        return 1

    print("")
    print("PASS: B4.1 host tests passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
