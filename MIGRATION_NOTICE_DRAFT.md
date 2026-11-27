# Advance notice: autoPlez is a separate Android app

**Draft for review only, not a public announcement. No new download is available.**

The unofficial Android updater fork is preparing a separate app called **autoPlez** (currently a test name). The current APK and its in-app updater stay on the old release channel. They will not offer autoPlez as a normal update.

When autoPlez is available, you will need to **install it once as a separate app**. Android does not transfer app data or sign-ins between these two app IDs. Keep the old app installed until you have signed in to the new app and checked that your libraries and playback work. On phones and tablets, Settings → Backup may help transfer some preferences. Save the file to a shared folder, then sign in and switch to the corresponding profile in the new app before importing. Use a separate file for each profile. Backup is not available on Android TV. autoPlez will have its own built-in updater for later autoPlez releases.

Before uninstalling the old app, open it while connected and confirm any recent watched status or playback progress has reached your media server. Downloads saved in the old app’s default offline folder won’t move over; re-download them in the new app. Don’t assume files in a custom shared folder will be picked up automatically.

When the new app is ready, this notice will point to install instructions. Until then, there is nothing you need to install. Existing copies of the old app will not receive a push notification from edits to this page.

## Rollout checklist (maintainers)

1. Keep the existing release and its `/releases/latest` feed unchanged; never add an autoPlez APK to the old feed or publish an APK there as a migration notice.
2. Confirm the public name and resolve any branding concerns before approving distribution. Confirm original artwork, new Android app ID, link scheme, independent service configuration, and a separate release repository before distributing anything.
3. After the public wording and destination are approved, post this advance notice prominently in the old project's README and current stable release notes **before** making the new download available. Those surfaces do not send push notifications to existing installs. Announce through any existing opt-in community channel only with permission. Verify both notices while signed out, record the public URLs and timestamps, and wait the agreed lead time from the later posting. Recommend at least seven days. If either notice is missing or the lead time has not elapsed, keep the download unavailable.
4. Publish autoPlez only on its separate feed, not as the latest old-fork release. Point the old-project notices to a migration landing page explaining the separate install before offering a download. Keep the old app usable side by side. Smoke-test the bridge on Android; verify TV migration separately before promising it.
5. In the new feed, name signed assets `autoplez-android-<ABI>.apk` to match the autoPlez selector, and verify all three against the actual release response. The rehearsal only stages synthetic metadata for unsigned APKs and never uses the legacy publisher or publishes assets.
6. Recheck that the old updater still sees 2.25.0, and that an installed autoPlez build accepts only correctly signed updates with the new app ID. Do not sign or publish this prototype.
