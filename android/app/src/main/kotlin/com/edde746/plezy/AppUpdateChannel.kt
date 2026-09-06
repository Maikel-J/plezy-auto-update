package com.edde746.plezy

import android.app.Activity
import android.content.ClipData
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Process
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * User-approved installation only. Android remains responsible for signature
 * verification and installation; no shell commands or broad storage access.
 */
internal class AppUpdateChannel(private val activity: Activity) {
  companion object {
    private const val PERMISSION_REQUEST = 7462
  }

  private var pendingPermission: MethodChannel.Result? = null
  private var channel: MethodChannel? = null
  private val updateDirectory get() = File(activity.cacheDir, "app-updates")

  fun attach(messenger: BinaryMessenger) {
    channel = MethodChannel(messenger, "com.plezy/app_update").also { channel ->
      channel.setMethodCallHandler(::onMethodCall)
    }
  }

  internal fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
    try {
      when (call.method) {
        "getSupportedAbis" -> result.success(
          // Stay with this installation's bitness. Flutter's per-ABI APKs
          // encode ABI offsets in versionCode; switching ABI can otherwise
          // look like a downgrade despite a newer semantic version.
          Build.SUPPORTED_ABIS.filter { it.contains("64") == Process.is64Bit() }
        )
        "requestInstallPermission" -> requestPermission(result)
        "prepareUpdateDirectory" -> {
          check(updateDirectory.isDirectory || updateDirectory.mkdirs()) { "Cannot create update cache" }
          // Only our two known filenames, never arbitrary cache contents.
          listOf("update.apk", "update.apk.part").forEach { name ->
            val file = File(updateDirectory, name)
            check(!file.exists() || file.delete()) { "Cannot clear previous update" }
          }
          result.success(updateDirectory.absolutePath)
        }
        "installUpdate" -> install(call.argument<String>("path"), result)
        else -> result.notImplemented()
      }
    } catch (error: Exception) {
      result.error("UPDATE_FAILED", error.message, null)
    }
  }

  private fun canInstall(): Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.O || activity.packageManager.canRequestPackageInstalls()

  private fun requestPermission(result: MethodChannel.Result) {
    if (pendingPermission != null) {
      result.error("UPDATE_BUSY", "An installation permission request is already active", null)
      return
    }
    if (canInstall()) {
      result.success(true)
      return
    }
    val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))
    // Keep no unresolved callback if this device has no settings handler.
    activity.startActivityForResult(intent, PERMISSION_REQUEST)
    pendingPermission = result
  }

  fun onActivityResult(requestCode: Int): Boolean {
    if (requestCode != PERMISSION_REQUEST) return false
    val result = pendingPermission
    pendingPermission = null
    try {
      result?.success(canInstall())
    } catch (error: Exception) {
      result?.error("UPDATE_FAILED", error.message, null)
    }
    return true
  }

  @Suppress("DEPRECATION")
  private fun install(path: String?, result: MethodChannel.Result) {
    val expected = File(updateDirectory, "update.apk").canonicalFile
    require(path != null && File(path).canonicalFile == expected && expected.isFile) { "Invalid update path" }
    if (!canInstall()) {
      result.error("INSTALL_PERMISSION_DENIED", "Allow installs from Plezy in Android settings", null)
      return
    }
    val pm = activity.packageManager
    val candidate = pm.getPackageArchiveInfo(expected.path, PackageManager.GET_SIGNATURES)
    if (candidate == null || candidate.packageName != activity.packageName) {
      result.error("INVALID_APK", "The APK is not an update for this application", null)
      return
    }
    val installed = pm.getPackageInfo(activity.packageName, PackageManager.GET_SIGNATURES)
    val newCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) candidate.longVersionCode else candidate.versionCode.toLong()
    val oldCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) installed.longVersionCode else installed.versionCode.toLong()
    if (newCode <= oldCode) {
      result.error("VERSION_NOT_NEWER", "The APK version code must be higher than the installed version", null)
      return
    }
    // The system verifies the actual APK signatures during installation. This
    // early comparison gives a useful error for fork/store signing mismatches.
    val oldSignatures = installed.signatures?.toSet()
    val newSignatures = candidate.signatures?.toSet()
    if (oldSignatures.isNullOrEmpty() || oldSignatures != newSignatures) {
      result.error("SIGNATURE_MISMATCH", "The APK must use the same signing key as this installation", null)
      return
    }
    val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.updates", expected)
    val intent = Intent(Intent.ACTION_VIEW).apply {
      setDataAndType(uri, "application/vnd.android.package-archive")
      clipData = ClipData.newRawUri("Plezy update", uri)
      addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    activity.startActivity(intent)
    // This means the confirmation UI opened, not that installation succeeded.
    result.success(null)
  }

  fun dispose() {
    channel?.setMethodCallHandler(null)
    channel = null
    pendingPermission?.error("ACTIVITY_DESTROYED", "Activity closed during installation permission request", null)
    pendingPermission = null
  }
}
