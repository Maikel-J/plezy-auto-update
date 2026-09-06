# Android release updates

GitHub/sideload Android builds check the latest **published, non-prerelease**
GitHub release on startup (when enabled in settings, at most once every six
hours) and through Settings → Check for Updates. A newer release offers
**Download and Install**. Skipping a version suppresses startup prompts only;
an explicit check can find it again.

The app streams the compatible APK into its private cache, checks its length
and GitHub's SHA-256 asset digest when present, and opens Android's installer.
On Android 8+, the first attempt asks for permission to install from Plezy and
continues when the user returns. Denial, download errors, cancellation, and
incompatible APKs leave the installed app untouched. Android always asks the
user to confirm installation; this is not a silent/background installer.

## Building and publishing

1. Keep a persistent Android release keystore. Configure the existing Build
   workflow's `ANDROID_KEYSTORE_BASE64`, `ANDROID_STORE_PASSWORD`,
   `ANDROID_KEY_PASSWORD`, and `ANDROID_KEY_ALIAS` secrets, or use your local
   `android/key.properties`. Never commit the keystore or its passwords.
2. Increase **both** the semantic version and the build number in
   `pubspec.yaml` (for example `2.18.1+148`). Release tags must match the version,
   optionally prefixed with `v`.
3. Build with:

   ```sh
   flutter build apk --release --split-per-abi \
     --dart-define=ENABLE_UPDATE_CHECK=true \
     --dart-define=ANDROID_UPDATE_REPOSITORY=Maikel-J/plezy-auto-update
   ```

4. Attach the standalone APKs to that repository's GitHub release using these
   exact names:

   | Build output | Release asset |
   | --- | --- |
   | `app-arm64-v8a-release.apk` | `plezy-android-arm64-v8a.apk` |
   | `app-armeabi-v7a-release.apk` | `plezy-android-armeabi-v7a.apk` |
   | `app-x86_64-release.apk` | `plezy-android-x86_64.apk` |

   A genuinely universal standalone APK can alternatively be named
   `plezy-android-universal.apk`. `.aab`, split APK sets, and `.tar.gz` archives
   cannot be installed by this flow.
5. Publish the release after attaching all assets. Drafts and prereleases are
   intentionally ignored. No releases means no available update.

The existing **Build** workflow now emits and attests these raw APKs alongside
the archives, points Android at the current repository, and includes them in
its draft release. Its existing release job still requires all platform builds;
for an Android-only build, download the `android-apk` Actions artifact and attach
the raw APKs to a release manually. No release is published automatically by
this feature.

## Installation requirements

- Install one build containing this updater manually first. An already-installed
  older app cannot acquire the updater until that first upgrade.
- All subsequent APKs must have the **same package ID and signing key**, and a
  strictly higher Android version code. Fork builds cannot update an upstream
  or Play-signed installation unless their signing keys match. Do not uninstall
  an existing app to work around this without first considering data loss.
- Keep the current installation's ABI/bitness; Flutter's ABI-specific version
  codes can make switching ABI appear to be a downgrade. Selection preserves
  process bitness and follows Android's supported ABI order.
- The update feature remains gated by `ENABLE_UPDATE_CHECK`. Without that flag,
  update UI is disabled. Gradle adds a sideload manifest overlay containing
  `REQUEST_INSTALL_PACKAGES` only for release builds with this flag. Store and
  ordinary debug/profile manifests do not request package installation.
- Android defaults to this fork's releases. Override
  `ANDROID_UPDATE_REPOSITORY=owner/repo` at build time for another fork. Desktop
  update feeds are unchanged.

## Verification

Run `flutter test test/services/android_update_service_test.dart
test/services/update_service_test.dart` and `flutter analyze`. On disposable
Android/Android TV devices, install a signed build, publish a newer matching
release, and verify: ABI selection; allow/deny install permission; cancel/back;
offline/truncated download; installer cancellation; successful update retaining
settings and sign-ins; and rejection of a differently signed or older APK.
Also inspect merged manifests with and without `ENABLE_UPDATE_CHECK=true`.

## Automatic releases from upstream

The **Upstream Android Releases** workflow checks `edde746/plezy` every hour
(at minute 17) and can also be started from Actions → Run workflow. Installing
or changing its workflow/helper on `main` starts the first build immediately.
It starts with upstream's latest published stable release; subsequent runs
process each new stable release in publication order, one per run. Drafts and
prereleases are excluded. Completed published fork releases record upstream
IDs, so failed builds/uploads are retried and completed releases are not rebuilt.

Each build merges the upstream release tag into an isolated checkout of this
fork's `main`, preserving the updater and other maintained fork changes. This
does not reset `main` to the upstream tag or erase existing unreleased fork work.
Merge conflicts require review and stop publication. Source is regenerated,
committed, tested, and signed before publishing a release such as
`v2.18.0+android.1`. The source tag includes the updater and build provenance;
the workflow does not push source merges or version bumps back to `main`.

The workflow requires four **repository Actions secrets**:
`ANDROID_KEYSTORE_BASE64`, `ANDROID_STORE_PASSWORD`, `ANDROID_KEY_PASSWORD`, and
`ANDROID_KEY_ALIAS`. Reuse the same private release key for all builds. Nothing
is published if any signing secret is absent. Workflow `GITHUB_TOKEN` handles
GitHub release uploads; no personal access token is required.

The three APKs, `SHA256SUMS`, and `upstream-release.json` are uploaded into a
draft first, then published together. The Android version code increases over
previous fork builds. If upload fails after tagging, the next attempt reuses
that exact tagged source instead of moving the tag.

Scheduled workflows must be enabled in Actions. GitHub may disable schedules
on inactive public repositories after 60 days; re-enable the workflow if that
happens. The existing multi-platform release workflow remains independent.
