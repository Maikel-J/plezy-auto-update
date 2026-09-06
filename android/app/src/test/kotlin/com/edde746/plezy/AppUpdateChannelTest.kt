package com.edde746.plezy

import android.app.Activity
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [25])
class AppUpdateChannelTest {
  @Test
  fun preOreoUsesSystemInstallerPermissionFlow() {
    val activity = Robolectric.buildActivity(Activity::class.java).get()
    val result = RecordingResult()
    AppUpdateChannel(activity).onMethodCall(MethodCall("requestInstallPermission", null), result)
    assertEquals(true, result.value)
    assertEquals(1, result.completions)
  }

  @Test
  fun preparationDeletesOnlyUpdaterOwnedFiles() {
    val activity = Robolectric.buildActivity(Activity::class.java).get()
    val directory = File(activity.cacheDir, "app-updates").apply { mkdirs() }
    File(directory, "update.apk").writeText("old APK")
    File(directory, "update.apk.part").writeText("partial")
    val unrelated = File(activity.cacheDir, "other-data").apply { writeText("keep") }
    val result = RecordingResult()
    AppUpdateChannel(activity).onMethodCall(MethodCall("prepareUpdateDirectory", null), result)
    assertEquals(directory.absolutePath, result.value)
    assertFalse(File(directory, "update.apk").exists())
    assertFalse(File(directory, "update.apk.part").exists())
    assertTrue(unrelated.exists())
  }

  @Test
  fun refusesArbitraryFilesOutsideUpdateCache() {
    val activity = Robolectric.buildActivity(Activity::class.java).get()
    val unrelated = File(activity.cacheDir, "untrusted.apk").apply { writeText("not an APK") }
    val result = RecordingResult()
    AppUpdateChannel(activity).onMethodCall(MethodCall("installUpdate", mapOf("path" to unrelated.path)), result)
    assertEquals("UPDATE_FAILED", result.errorCode)
    assertEquals(1, result.completions)
    assertTrue(unrelated.exists())
  }

  @Test
  fun invalidApkIsNotHandedToInstaller() {
    val activity = Robolectric.buildActivity(Activity::class.java).get()
    val directory = File(activity.cacheDir, "app-updates").apply { mkdirs() }
    val apk = File(directory, "update.apk").apply { writeText("not an APK") }
    val result = RecordingResult()
    AppUpdateChannel(activity).onMethodCall(MethodCall("installUpdate", mapOf("path" to apk.path)), result)
    assertEquals("INVALID_APK", result.errorCode)
    assertEquals(1, result.completions)
  }

  @Test
  fun destroyCompletesPendingPermissionExactlyOnce() {
    val activity = Robolectric.buildActivity(Activity::class.java).get()
    val channel = AppUpdateChannel(activity)
    val result = RecordingResult()
    channel.javaClass.getDeclaredField("pendingPermission").apply {
      isAccessible = true
      set(channel, result)
    }
    channel.dispose()
    channel.dispose()
    assertEquals("ACTIVITY_DESTROYED", result.errorCode)
    assertEquals(1, result.completions)
    assertFalse(channel.onActivityResult(123))
  }

  private class RecordingResult : MethodChannel.Result {
    var completions = 0
    var value: Any? = null
    var errorCode: String? = null

    override fun success(result: Any?) {
      value = result
      completions++
    }

    override fun error(errorCode: String, errorMessage: String?, errorDetails: Any?) {
      this.errorCode = errorCode
      completions++
    }

    override fun notImplemented() {
      completions++
    }
  }
}
