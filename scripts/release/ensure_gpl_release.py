#!/usr/bin/env python3
"""Normalize fork Android releases with explicit GPL/source notices."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

UPSTREAM = "edde746/plezy"
TAG = re.compile(r"^v(\d+\.\d+\.\d+)\+android\.(\d+)$")
MARKER = re.compile(r"<!-- plezy-upstream:\d+ published:[^ ]+ build:\d+ -->")
NOTICE = re.compile(
    r"\n?<!-- gpl-release-notice:start -->.*?<!-- gpl-release-notice:end -->\n?",
    re.DOTALL,
)


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def releases(repo: str) -> list[dict]:
    return json.loads(run("gh", "api", f"repos/{repo}/releases?per_page=100"))


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    license_path = Path("LICENSE")
    if not license_path.is_file():
        raise SystemExit("LICENSE is required before release normalization")

    for release in releases(repo):
        tag = release.get("tag_name", "")
        match = TAG.fullmatch(tag)
        body = release.get("body") or ""
        if not match or not MARKER.search(body):
            continue

        version = match.group(1)
        body = NOTICE.sub("\n", body).rstrip()
        date = (release.get("published_at") or release.get("created_at") or "unknown")[:10]
        source_url = f"https://github.com/{repo}/tree/{tag}"
        notice = (
            "\n\n<!-- gpl-release-notice:start -->\n"
            "## License and source\n\n"
            "This is an **unofficial modified build of Plezy**. It includes Android self-update "
            "support maintained by this fork and is distributed under the **GNU General Public "
            "License, version 3 (GPL-3.0)**.\n\n"
            f"Corresponding source for this exact binary release: {source_url}\n\n"
            f"Upstream project: https://github.com/{UPSTREAM}\n\n"
            f"Modification/release date: {date}\n\n"
            "The GPL-3.0 license is attached to this release as `LICENSE` and is also included "
            "in the corresponding source tree.\n"
            "<!-- gpl-release-notice:end -->\n"
        )

        title = release.get("name") or f"Plezy {version} — Android auto-update"
        if not title.startswith("Unofficial "):
            title = "Unofficial " + title

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as notes:
            notes.write(body + notice)
            notes_path = Path(notes.name)
        try:
            subprocess.run(
                ["gh", "release", "edit", tag, "--repo", repo, "--title", title,
                 "--notes-file", str(notes_path)],
                check=True,
            )
            subprocess.run(
                ["gh", "release", "upload", tag, "--repo", repo, "--clobber", str(license_path)],
                check=True,
            )
        finally:
            notes_path.unlink(missing_ok=True)

        print(f"Normalized GPL/source notice for {tag}")


if __name__ == "__main__":
    main()
