#!/usr/bin/env python3
"""
Tests for the declared-scope vs. enforced-scope demo.

    python3 -m unittest demo/test_scope_enforcement_gap.py -v

Stdlib only. Python 3.9+.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scope_enforcement_gap import (  # noqa: E402
    CANARY, NaiveHarness, VerifiedHarness, WikiTarget,
)


def reads(n, prefix="Talk:Page"):
    return [{"endpoint": "view", "resource": f"{prefix}_{i}"} for i in range(n)]


class NaiveHarnessTest(unittest.TestCase):
    """The naive harness enforces its own labels correctly. That is the point:
    it is not broken at what it measures, it is measuring the wrong thing."""

    def test_declared_writes_are_refused_regardless_of_target(self):
        target = WikiTarget(enforces_read_only=False)
        requests = reads(2) + [{"endpoint": "edit", "resource": "Talk:Page_0"}]
        result = NaiveHarness(target).run(requests)
        self.assertEqual(len(result.refused), 1)
        self.assertEqual(result.refused[0]["endpoint"], "edit")

    def test_reads_against_a_conforming_target_change_nothing(self):
        target = WikiTarget(enforces_read_only=True)
        before = target.fingerprint()
        result = NaiveHarness(target).run(reads(5))
        self.assertEqual(len(result.performed), 5)
        self.assertFalse(result.halted)
        self.assertEqual(target.fingerprint(), before)
        self.assertEqual(target.posts, {})

    def test_declared_read_only_run_writes_at_the_scale_of_the_batch(self):
        target = WikiTarget(enforces_read_only=False)
        result = NaiveHarness(target).run(reads(500))
        # The harness reports a clean read-only run...
        self.assertEqual(len(result.performed), 500)
        self.assertFalse(result.halted)
        # ...and the target recorded a post for every one of them. Nothing
        # ever checks, so the damage scales with the batch.
        self.assertEqual(len(target.posts), 500)


class VerifiedHarnessTest(unittest.TestCase):
    """The verified harness measures the target instead of its own labels."""

    def test_probe_detects_that_the_target_does_not_enforce_the_scope(self):
        enforcing = VerifiedHarness(WikiTarget(enforces_read_only=True))
        divergent = VerifiedHarness(WikiTarget(enforces_read_only=False))
        self.assertTrue(enforcing.probe("view"))
        self.assertFalse(divergent.probe("view"))

    def test_run_halts_before_touching_real_resources_when_probe_fails(self):
        target = WikiTarget(enforces_read_only=False)
        result = VerifiedHarness(target).run(reads(500))
        self.assertTrue(result.halted)
        self.assertEqual(result.performed, [])
        self.assertIn("diverge", result.reason)
        # Blast radius: the single canary write the probe itself cost.
        self.assertEqual(len(target.posts), 1)
        self.assertTrue(all(k.startswith(CANARY) for k in target.posts))

    def test_run_proceeds_once_the_target_is_shown_to_enforce_the_scope(self):
        target = WikiTarget(enforces_read_only=True)
        result = VerifiedHarness(target).run(reads(5))
        self.assertFalse(result.halted)
        self.assertEqual(len(result.performed), 5)
        self.assertEqual(target.posts, {})

    def test_a_passing_probe_is_evidence_not_a_standing_permission(self):
        target = WikiTarget(enforces_read_only=True)
        harness = VerifiedHarness(target)
        self.assertTrue(harness.probe("view"))
        # The target's behaviour changes after the probe — a config flip, a
        # deploy, a different code path behind the same endpoint.
        target.enforces_read_only = False
        result = harness.run(reads(500))
        self.assertTrue(result.halted)
        self.assertIn("state changed", result.reason)
        # Halted on the first real state change: one post, not five hundred.
        self.assertEqual(len(result.performed), 0)
        self.assertEqual(len(target.posts), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
