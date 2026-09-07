#!/usr/bin/env python3
"""Discover stable upstream releases and prepare reproducible fork Android builds.

GitHub releases, not a local marker or successful build, are the completion
record. A failed build/upload is retried without skipping the upstream release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

UPSTREAM = "edde746/plezy"
MARKER = re.compile(r"<!-- plezy-upstream:(\d+) published:([^ ]+) build:(\d+) -->")
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
PROVENANCE = Path(".github/android-release-source.json")
GENERATED_TRANSLATIONS = {
    "lib/i18n/strings.g.dart",
    "lib/i18n/strings_en.g.dart",
}
# One-off updater validation build. This commit is reverted immediately after
# the workflow is queued so normal hourly discovery remains unchanged.
FORCE_UPSTREAM_TAG = "2.19.0"
FORCE_PREVIOUS_BUILD = 148


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


def git(*args: str) -> str:
    return run("git", *args).stdout.strip()


def api(path: str) -> object:
    return json.loads(run("gh", "api", path).stdout)


def releases(repo: str) -> list[dict]:
    result = []
    page = 1
    while True:
        batch = api(f"repos/{repo}/releases?per_page=100&page={page}")
        result.extend(batch)
        if len(batch) < 100:
            return result
        page += 1


def version(tag: str) -> str:
    match = VERSION.fullmatch(tag)
    if not match:
        raise ValueError(f"Unsupported upstream release tag: {tag!r}")
    return ".".join(str(int(part)) for part in match.groups())


def is_latest_version(candidate: str, own: list[dict]) -> bool:
    current = tuple(map(int, candidate.split(".")))
    for release in own:
        if release["draft"] or release["prerelease"]:
            continue
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\+android\.\d+", release["tag_name"])
        if match and tuple(map(int, match.groups())) > current:
            return False
    return True


def select_release(upstream: list[dict], own: list[dict], latest_id: int) -> dict | None:
    stable = [r for r in upstream if not r["draft"] and not r["prerelease"]]
    completed = [MARKER.search(r.get("body") or "") for r in own if not r["draft"] and not r["prerelease"]]
    completed = [match for match in completed if match]
    if not completed:
        # Bootstrap from the current stable release, not the entire history.
        return next((r for r in stable if r["id"] == latest_id), None)
    done = {int(match[1]) for match in completed}
    bootstrap = min(match[2] for match in completed)
    pending = [r for r in stable if r["id"] not in done and r["published_at"] >= bootstrap]
    # Process one queued release per run, oldest first, so polling cannot skip
    # intermediate releases if multiple versions appear between checks.
    return min(pending, key=lambda r: (r["published_at"], r["id"]), default=None)


def discover(plan_path: Path) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or repo == UPSTREAM:
        raise ValueError("This workflow must run in the fork repository")
    own = releases(repo)
    upstream = releases(UPSTREAM)
    latest = api(f"repos/{UPSTREAM}/releases/latest")
    if FORCE_UPSTREAM_TAG:
        release = next(
            (
                r
                for r in upstream
                if r["tag_name"] == FORCE_UPSTREAM_TAG
                and not r["draft"]
                and not r["prerelease"]
            ),
            None,
        )
        if release is None:
            raise ValueError(f"Cannot find forced upstream release {FORCE_UPSTREAM_TAG}")
    else:
        release = select_release(upstream, own, latest["id"])
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"pending={'true' if release else 'false'}\n")
    if release is None:
        print("Every stable upstream release since bootstrap has been published.")
        return
    release_version = version(release["tag_name"])
    previous_builds = [int(m[3]) for r in own if (m := MARKER.search(r.get("body") or ""))]
    plan = {
        "repository": repo,
        "upstream_repository": UPSTREAM,
        "upstream_release_id": release["id"],
        "upstream_tag": release["tag_name"],
        "upstream_published_at": release["published_at"],
        "upstream_url": release["html_url"],
        "version": release_version,
        "release_tag": f"v{release_version}+android.1",
        "previous_build": FORCE_PREVIOUS_BUILD
        if FORCE_UPSTREAM_TAG
        else max(previous_builds, default=0),
    }
    collisions = [r for r in own if r["tag_name"] == plan["release_tag"]]
    if collisions and not all(r["draft"] and MARKER.search(r.get("body") or "") for r in collisions):
        raise ValueError("Release tag is already owned by a different or published release")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Selected {UPSTREAM} {plan['upstream_tag']} -> {plan['release_tag']}")


def prepare(plan_path: Path) -> None:
    plan = json.loads(plan_path.read_text())
    tag_ref = f"refs/tags/{plan['release_tag']}"
    existing = git("ls-remote", "--refs", "origin", tag_ref)
    if existing:
        # Recover an upload failure using the exact previously tagged source.
        git("fetch", "--no-tags", "origin", tag_ref)
        commit = git("rev-parse", "FETCH_HEAD^{commit}")
        saved = json.loads(git("show", f"{commit}:{PROVENANCE.as_posix()}"))
        if saved["upstream_release_id"] != plan["upstream_release_id"]:
            raise ValueError("Existing tag belongs to another upstream release")
        git("checkout", "--detach", commit)
        plan.update(saved)
        plan["retry_tag"] = True
    else:
        plan["fork_base_sha"] = git("rev-parse", "HEAD")
        git("fetch", "--no-tags", f"https://github.com/{UPSTREAM}.git", f"refs/tags/{plan['upstream_tag']}")
        upstream_sha = git("rev-parse", "FETCH_HEAD^{commit}")
        plan["upstream_sha"] = upstream_sha
        merge = run("git", "merge", "--no-commit", "--no-ff", upstream_sha, check=False)
        if merge.returncode:
            conflicts = set(filter(None, git("diff", "--name-only", "--diff-filter=U").splitlines()))
            unexpected = conflicts - GENERATED_TRANSLATIONS
            if unexpected:
                raise RuntimeError(
                    "Upstream merge needs review; no release will be published:\n"
                    + "\n".join(sorted(conflicts))
                    + f"\n{merge.stderr}"
                )
            if not conflicts:
                raise RuntimeError(f"Upstream merge failed without merge conflicts:\n{merge.stderr}")
            # These files are generated from the merged translation sources. Take
            # upstream's generated snapshots only to finish the merge; codegen runs
            # immediately afterwards and regenerates the authoritative output.
            run("git", "checkout", "--theirs", "--", *sorted(conflicts))
            run("git", "add", "--", *sorted(conflicts))
        pubspec = Path("pubspec.yaml")
        text = pubspec.read_text()
        match = re.search(r"(?m)^version: ([^\s+]+)\+(\d+)\s*$", text)
        if not match:
            raise ValueError("pubspec.yaml must have a semantic version and Android build number")
        plan["build_number"] = max(int(match[2]) + 1, plan["previous_build"] + 1)
        text = text[:match.start()] + f"version: {plan['version']}+{plan['build_number']}\n" + text[match.end():]
        pubspec.write_text(text)
        PROVENANCE.write_text(json.dumps(plan, indent=2) + "\n")
        git("add", "pubspec.yaml", str(PROVENANCE))
    workflow = Path(".github/workflows/build.yml").read_text()
    sdk = re.search(r'''(?m)^\s*FLUTTER_VERSION:\s*["'](\d+\.\d+\.\d+)["']\s*$''', workflow)
    if not sdk:
        raise ValueError("Cannot resolve the merged source's pinned Flutter version")
    plan["flutter_version"] = sdk[1]
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"flutter_version={sdk[1]}\n")
    verify_updater()


def verify_updater() -> None:
    # An upstream merge must not silently remove the fork's update integration.
    checks = {
        "lib/services/update_service.dart": ["ANDROID_UPDATE_REPOSITORY", "AndroidUpdateAsset.select"],
        "lib/utils/update_dialog.dart": ["downloadAndInstall"],
        "android/app/src/main/kotlin/com/edde746/plezy/MainActivity.kt": ["appUpdateChannel.attach"],
        "android/app/src/main/kotlin/com/edde746/plezy/AppUpdateChannel.kt": ["installUpdate", "SIGNATURE_MISMATCH"],
        "android/app/src/sideload/AndroidManifest.xml": ["android.permission.REQUEST_INSTALL_PACKAGES"],
    }
    for name, required in checks.items():
        content = Path(name).read_text()
        if not all(token in content for token in required):
            raise ValueError(f"Upstream merge removed required updater behavior in {name}")


def commit_source(plan_path: Path) -> None:
    plan = json.loads(plan_path.read_text())
    if plan.get("retry_tag"):
        if git("status", "--porcelain", "--untracked-files=no"):
            raise ValueError("Regeneration changed previously tagged source; refusing to change the release")
    else:
        # Commit regenerated files along with the upstream merge and version.
        git("add", "-u")
        git("commit", "-m", f"build(android): upstream {plan['upstream_tag']} with release updater")
    plan["source_sha"] = git("rev-parse", "HEAD")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")


def publish(plan_path: Path, assets: Path) -> None:
    plan = json.loads(plan_path.read_text())
    repo, tag = plan["repository"], plan["release_tag"]
    paths = [assets / f"plezy-android-{abi}.apk" for abi in ("arm64-v8a", "armeabi-v7a", "x86_64")]
    if any(not p.is_file() or p.stat().st_size == 0 for p in paths):
        raise ValueError("All three signed APKs must exist before publishing")
    if git("rev-parse", "HEAD") != plan["source_sha"]:
        raise ValueError("Build source moved before publishing")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Build changed tracked source; refusing to publish mismatched source")
    if not plan.get("retry_tag"):
        git("push", "origin", f"{plan['source_sha']}:refs/tags/{tag}")
    marker = f"<!-- plezy-upstream:{plan['upstream_release_id']} published:{plan['upstream_published_at']} build:{plan['build_number']} -->"
    notes = assets / "release-notes.md"
    notes.write_text(
        f"Android build of this fork incorporating [{plan['upstream_tag']}]({plan['upstream_url']}) and the in-app updater.\n\n"
        "Install the APK for your device. Future stable upstream releases are rebuilt automatically. "
        "Android asks you to approve installation. Updates require the same signing key; the first updater-enabled build must be installed manually.\n\n"
        f"Source: `{plan['source_sha']}`\n\nAndroid build number: {plan['build_number']}\n\n{marker}\n"
    )
    own = releases(repo)
    existing = next((r for r in own if r["tag_name"] == tag), None)
    if existing and not existing["draft"]:
        raise ValueError("Refusing to modify an already published release")
    if existing is None:
        run("gh", "release", "create", tag, "--repo", repo, "--verify-tag", "--draft", "--title",
            f"Plezy {plan['version']} — Android auto-update", "--notes-file", str(notes))
    # Upload into a draft; mark completion only after all assets are present.
    manifest = assets / "upstream-release.json"
    manifest.write_text(json.dumps(plan, indent=2) + "\n")
    run("gh", "release", "upload", tag, "--repo", repo, "--clobber", *map(str, paths), str(manifest), str(assets / "SHA256SUMS"))
    latest = "true" if is_latest_version(plan["version"], own) else "false"
    run("gh", "release", "edit", tag, "--repo", repo, "--notes-file", str(notes), "--draft=false", f"--latest={latest}")
    print(f"Published https://github.com/{repo}/releases/tag/{tag}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["discover", "prepare", "commit-source", "publish"])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--assets", type=Path)
    args = parser.parse_args()
    if args.command == "discover":
        discover(args.plan)
    elif args.command == "prepare":
        prepare(args.plan)
    elif args.command == "commit-source":
        commit_source(args.plan)
    else:
        if args.assets is None:
            parser.error("publish requires --assets")
        publish(args.plan, args.assets)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Command failed ({error.returncode}): {error.stderr}") from error
