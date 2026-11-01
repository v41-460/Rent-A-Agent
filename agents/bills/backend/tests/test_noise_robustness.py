"""Every scenario again, with different everyday spending around the bills.

Random grocery runs, restaurant visits and online orders must never turn into
bills. Run with BILLS_NOISE_SEEDS=1000 for the long version.
"""

import os

import pytest

from bills_agent.detection import detect_bills
from bills_fixtures import scenarios
from bills_fixtures.builder import ACCOUNT_NAMES

from .test_scenarios import _check, _describe

SEEDS = range(1000, 1000 + int(os.environ.get("BILLS_NOISE_SEEDS", "25")))


@pytest.mark.parametrize("make", scenarios.ALL, ids=lambda f: f.__name__)
def test_scenario_survives_different_noise(make):
    failures = []
    for seed in SEEDS:
        s = make(seed)
        result = detect_bills(s.transactions, s.as_of, ACCOUNT_NAMES)
        problems = _check(s, result)
        if problems:
            failures.append(f"seed {seed}: " + "; ".join(problems) + "\n" + _describe(result))
    assert not failures, "\n\n".join(failures[:3])
