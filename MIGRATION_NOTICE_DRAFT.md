# Advance notice: Sundock Media is a separate Android app

**Draft for review. Sundock Media is not available yet.**

The unofficial Android updater fork is moving to a new app called **Sundock Media** (working name). The current APK and its in-app updater stay on the old release channel. They will not offer Sundock as a normal update.

When Sundock is available, you will need to **install it once as a separate app**. Android does not transfer app data or sign-ins between these two app IDs. Keep the old app installed until you have signed in to the new app and checked that your libraries and playback work. On phones and tablets, Settings → Backup may transfer supported preferences; it excludes sign-ins, and that menu is not available on Android TV. Do not tell users to uninstall first. Sundock will have its own built-in updater for later Sundock releases.

## Rollout checklist (maintainers)

1. Keep the existing release and its `/releases/latest` feed unchanged; never add a Sundock APK to the old feed or publish an APK there as a migration notice.
2. Confirm the new app name, original artwork, new Android app ID, link scheme, independent service configuration, and a separate release repository before distributing anything.
3. After the public wording and destination are approved, post this advance notice prominently in the old project's README and current stable release notes **before** making the new download available. Those surfaces do not send push notifications to existing installs. Announce through any existing opt-in community channel only with permission. Record the notice URLs and posting time, and agree a lead time before release.
4. Publish Sundock only on its separate feed, not as the latest old-fork release. Point the old-project notices to a migration landing page explaining the separate install before offering a download. Keep the old app usable side by side. Smoke-test the bridge on Android; verify TV migration separately before promising it.
5. Recheck that the old updater still sees 2.25.0, and that an installed Sundock build accepts only correctly signed updates with the new app ID. Do not sign or publish this prototype.
