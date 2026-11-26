from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import upstream_android as release


class ReleaseAncestryTest(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.repo = Path(workspace.name)
        mock = patch.object(release, "run", side_effect=self.command)
        mock.start()
        self.addCleanup(mock.stop)
        self.git("init", "-b", "upstream")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Release ancestry test")
        self.old = self.commit("upstream-2.25")
        self.tag = self.commit("upstream-2.26")
        self.tip = self.commit("post-2.26-upstream")

    def command(self, *args, check=True):
        return subprocess.run(args, cwd=self.repo, check=check, text=True, capture_output=True)

    def git(self, *args):
        return self.command("git", *args).stdout.strip()

    def commit(self, name):
        self.git("commit", "--allow-empty", "-m", name)
        return self.git("rev-parse", "HEAD")

    def fork(self, base):
        self.git("checkout", "--detach", base)
        return self.commit("fork-only updater changes")

    def test_fork_from_previous_release_is_allowed(self):
        release.verify_release_ancestry(self.fork(self.old), self.tag, self.tip)

    def test_fork_based_on_exact_tag_is_allowed(self):
        release.verify_release_ancestry(self.fork(self.tag), self.tag, self.tip)

    def test_fork_with_newer_upstream_commit_is_rejected(self):
        # Reproduction of the risk after sync: the older tag is already an
        # ancestor so a subsequent merge would leave the newer source intact.
        head = self.fork(self.tip)
        self.git("merge-base", "--is-ancestor", self.tag, head)
        with self.assertRaisesRegex(ValueError, "outside the selected release"):
            release.verify_release_ancestry(head, self.tag, self.tip)

    def test_unrelated_fork_is_rejected(self):
        self.git("checkout", "--orphan", "unrelated")
        with self.assertRaisesRegex(ValueError, "Cannot establish"):
            release.verify_release_ancestry(self.commit("unrelated fork"), self.tag, self.tip)
