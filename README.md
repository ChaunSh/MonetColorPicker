# Wallpaper Monet ADB Studio

Windows 图形工具：壁纸导入 → 按手机屏幕纵向比例裁切（拖动/缩放）→ 图片导出 → 从裁切图片或原图中计算 Material You / Monet 主色 → 预览/导出 65 色 → ADB 写入主题设置 → 回读验证/恢复原值。

## 运行环境

- Windows 10/11，Python **3.10 或更新版本**（建议 3.11/3.12）。
- 安装了 Android Platform Tools（`adb.exe`），加入 PATH，或者在 GUI 中指定位置。下载：<https://developer.android.com/tools/releases/platform-tools>
- 手机上开启开发者选项和 **USB 调试**，连接 USB 并在手机上确认电脑的 RSA 调试授权。**无需 Root**。
- 自动安装的 Python 依赖：`Pillow`、`materialyoucolor`。初次安装需要联网。

## 一键启动

解压文件夹后，双击 **`run_windows.bat`**。脚本在当前文件夹中创建 `.venv` 虚拟环境，安装依赖，启动程序。

或命令行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

需要打包独立的 Windows EXE 时，在 Windows 上运行 `build_windows_exe.bat`（PyInstaller），生成 `dist\WallpaperMonetADB.exe`。这个 EXE **不会打包 adb.exe**，仍需要配置 Android Platform Tools。

## 操作流程

1. 选择图片。程序读取 EXIF 方向，支持 PNG、JPG、WEBP 等，透明像素按白色背景合成。
2. 点击 **刷新设备**，选择已授权的 ADB 设备，再点击 **从手机读取** 获取纵向屏幕分辨率；或手动输入目标宽高。
3. 默认启用 **按屏幕比例裁切**。拖动青色框改变内容，调整缩放滑块或滚轮调整裁切区域；可设置 **导出时缩放至屏幕分辨率**。取消“按屏幕比例裁切”时，导出和取色均使用整张原图（不缩放）。
4. 点击 **导出图片** 保存 PNG、JPG 或 WEBP。
5. 点击 **分析图片颜色**；使用 Celebi 量化 + Material You Score 取出候选 Seed Colors。点击候选色切换源色；右侧显示 5×13 色阶。可将色阶导出 JSON。
6. 点击 **写入选定主色**，确认设备、源色与主题变体。程序会先保存原始 Android Secure Setting，然后写入并再次读取验证。
7. 点击 **恢复最近备份**，回滚该设备写入前的 Secure Setting。备份位置：`%USERPROFILE%\.wallpaper_monet_adb\backups\`。

## 重要限制：HyperOS / MIUI

**ADB 写入成功 ≠ 小米系统界面实际应用 Monet。** 本工具使用 Android AOSP 的 `Settings.Secure.THEME_CUSTOMIZATION_OVERLAY_PACKAGES` 接口：

```json
{
  "android.theme.customization.system_palette": "746BC1",
  "android.theme.customization.theme_style": "TONAL_SPOT"
}
```

如果 ROM 的 SystemUI / ThemeManager 不监听该接口，ADB 回读虽然一致，状态栏、控制中心、系统桌面等也可能完全不变。这不是算法错误，也无法用非 Root ADB 保证解决。本工具**不**改写系统私有数据库、不重启 SystemUI、不安装模块，也**不会**自动更换手机当前壁纸。

> 小米的 Monet 行为可能与 AOSP 不同；请先确认手机设置内是否有壁纸配色/主题配色开关。如写入后变化不明显，可以重新打开使用动态配色的应用进行观察。

## 算法说明

- 主色提取：`materialyoucolor.quantize.ImageQuantizeCelebi` + `materialyoucolor.score.score.Score`，处理前缩小至 520px 以提高响应速度。量化结果与手机 ROM 对原图所用的采样、过滤、厂商权重可能不同。
- 本地预览：Material You 2021 版本的 HCT tonal palette（以匹配 Android 12 经典配色）。`SPRITZ` 使用库中的 `SchemeNeutral` 作为对应的低饱和度方案。
- 65 色 JSON **仅供预览/导出**；写入 Android 是 seed color + style，不是逐个写 65 个资源。
- `MONOCHROMATIC`、`RAINBOW` 等变体的实际行为取决于 ROM Android 版本。

## 数据与安全

- 不上传图片，不接入第三方在线服务。所有颜色运算本地执行。
- 子进程调用 `adb` 时不使用 `shell=True`，设备目标通过 ADB `-s` 绑定；远程设置值使用 shell 安全引用。
- 每次写入前自动备份，包含**完整旧设置原文**，支持恢复；不保证 ROM 一定采纳主题颜色。
- 程序会修改手机的主题设置。先保存现有设置再写入；如果设备有特殊主题管理功能，系统或主题应用可随后覆盖此项。

## 已知注意事项

- 高分辨率图片的初次渲染可能花费一点时间；分析算法在线程中计算。
- 无法仅凭 `settings get` 判断系统所有界面是否更新；需要在设备上人工确认。
- 如果 ADB 显示 `unauthorized`，在手机上接受 USB 调试授权后刷新设备。

## 官方文档

- AOSP 动态配色：<https://source.android.com/docs/core/display/dynamic-color>
- AOSP Material You：<https://source.android.com/docs/core/display/material>
- Material You Python 算法：<https://github.com/T-Dynamos/materialyoucolor-python>

## 无线调试与安卓伴侣

Android 11 及以上可在手机开发者选项中打开“无线调试”。点击桌面端“无线调试”，先输入手机“使用配对码配对设备”页面上的配对地址和配对码，配对后再输入无线调试主页显示的连接地址；这两个端口通常不同。连接后刷新设备并选中手机。手机和电脑需处于可互通的网络中。

安卓伴侣源码、构建与安装步骤见 [android/README.md](android/README.md)。安装并打开伴侣，授予“管理所有文件”权限后，在桌面端选择已授权设备并点击“读取手机壁纸”。支持主屏静态壁纸；动态壁纸、锁屏壁纸或厂商限制的壁纸可能无法读取。导出图像会重编码，不保证与原始文件一致。伴侣将图像和状态保存在手机共享下载目录 `Download/WallpaperMonet`，其他应用可能访问，使用后可自行删除。
