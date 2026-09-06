#!/usr/bin/env python3
"""Behavior checks for release discovery, completion tracking, and safe retries."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("upstream_android", Path(__file__).with_name("upstream_android.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def release(identity, date, **changes):
    return {"id": identity, "published_at": date, "draft": False, "prerelease": False,
            "tag_name": f"2.18.{identity}", **changes}


def completed(identity, date, **changes):
    return {"draft": False, "prerelease": False,
            "body": f"<!-- plezy-upstream:{identity} published:{date} build:148 -->", **changes}


class DiscoveryTest(unittest.TestCase):
    def test_first_run_builds_only_latest_stable(self):
        releases = [release(1, "2026-08-01T00:00:00Z"), release(2, "2026-08-02T00:00:00Z")]
        self.assertEqual(module.select_release(releases, [], 2)["id"], 2)

    def test_ignores_upstream_drafts_and_prereleases(self):
        releases = [release(2, "2026-08-02T00:00:00Z", prerelease=True),
                    release(3, "2026-08-03T00:00:00Z", draft=True)]
        self.assertIsNone(module.select_release(releases, [], 2))

    def test_checks_each_missed_release_in_order(self):
        releases = [release(4, "2026-08-04T00:00:00Z"), release(3, "2026-08-03T00:00:00Z"),
                    release(2, "2026-08-02T00:00:00Z"), release(1, "2026-08-01T00:00:00Z")]
        own = [completed(2, "2026-08-02T00:00:00Z")]
        self.assertEqual(module.select_release(releases, own, 4)["id"], 3)
        own.append(completed(3, "2026-08-03T00:00:00Z"))
        self.assertEqual(module.select_release(releases, own, 4)["id"], 4)

    def test_published_release_is_not_rebuilt(self):
        date = "2026-08-02T00:00:00Z"
        self.assertIsNone(module.select_release([release(2, date)], [completed(2, date)], 2))

    def test_failed_draft_is_retried(self):
        date = "2026-08-02T00:00:00Z"
        self.assertEqual(module.select_release([release(2, date)], [completed(2, date, draft=True)], 2)["id"], 2)

    def test_unrelated_fork_release_does_not_mark_upstream_done(self):
        own = [{"draft": False, "prerelease": False, "body": "Manual release"}]
        self.assertEqual(module.select_release([release(2, "2026-08-02T00:00:00Z")], own, 2)["id"], 2)

    def test_tags_must_be_plain_semantic_versions(self):
        self.assertEqual(module.version("v2.18.0"), "2.18.0")
        self.assertEqual(module.version("2.18.0"), "2.18.0")
        for bad in ["../main", "2.18.0;echo secret", "-x", "2.18", "2.18.0-rc1"]:
            with self.assertRaises(ValueError):
                module.version(bad)


if __name__ == "__main__":
    unittest.main()
