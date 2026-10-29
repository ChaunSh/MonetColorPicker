# Wallpaper Monet 安卓伴侣

需要 Android 11（API 30）或更高。使用 Android Studio 打开本目录，安装 Android SDK 36、JDK 17 和 Gradle，然后构建 `app` 的 debug APK（`gradle assembleDebug`）；也可使用 Android Studio 的 Build APK。安装后先手动打开应用，点击“管理所有文件权限”并在系统设置中授权，然后在手机开启 ADB 调试并授权电脑。

桌面程序可通过 ADB 触发导出主屏静态壁纸。系统、Android 版本或厂商可能禁止访问真实壁纸；动态壁纸不支持导出，锁屏壁纸不在本应用的范围。该权限不能突破系统和厂商的所有壁纸保护。导出是图像重编码，可能与原始文件不同。

ADB 协议：在授权设备上发送 `adb shell am broadcast -n com.wallpapermonet.companion/.ExportReceiver -a com.wallpapermonet.companion.EXPORT`，广播结束后读取 `/sdcard/Download/WallpaperMonet/status.txt`，仅当内容为 `OK` 时读取同目录 `wallpaper.png`；失败则状态以 `ERROR:` 开头。接收器使用系统 `android.permission.DUMP` 限制调用；首次使用必须先从手机打开应用，避免系统阻止处于停止状态的应用接收广播。

导出文件放在共享下载目录，可能被其他应用访问；传输结束后请删除它。卸载应用不会自动删除共享目录中的导出文件。请仅在可信设备和可信 ADB 连接上使用。

应用首页在 Android 12 及以上展示系统提供的五组动态配色，每组 13 个色阶；点击色块查看对应资源名和 HEX 色值。色阶反映当前系统资源，可能受壁纸、系统主题与厂商实现影响，与桌面端基于图片计算的预览不一定一致。Android 11 无系统动态色资源，将显示不可用提示。

主界面的“当前系统动态配色”在 Android 12 及以上展示系统提供的五组色阶，点击色块可查看资源名和十六进制色值。配色受系统设置和厂商实现影响，未必完全对应当前壁纸；Android 11 不提供这一组系统资源。
