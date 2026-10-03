#!/usr/bin/env python3
"""
Wobble Test Runner
Executes the full automated test suite and reports results.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


def run_all_tests() -> bool:
    print("\n=======================================================")
    print("             RUNNING WOBBLE TEST SUITE                 ")
    print("=======================================================\n")

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(Path(__file__).parent), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n-------------------------------------------------------")
    print(f"Tests run: {result.testsRun} | Failures: {len(result.failures)} | Errors: {len(result.errors)}")
    print("=======================================================\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
