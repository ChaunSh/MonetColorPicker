"""ADB transport for the Android companion's explicitly requested export."""
from pathlib import Path
import tempfile
from core import open_image
from adb_tools import AdbError

REMOTE_DIR = "/sdcard/Download/WallpaperMonet"

def fetch_wallpaper(adb):
    # Clear the completion marker so an old export cannot be mistaken for a new one.
    adb.shell(f"rm -f {REMOTE_DIR}/status.txt")
    response = adb.shell("am broadcast -n com.wallpapermonet.companion/.ExportReceiver "
                         "-a com.wallpapermonet.companion.EXPORT")
    if "Broadcast completed" not in response:
        raise AdbError(f"伴侣应用没有完成导出：{response}")
    status = adb.shell(f"cat {REMOTE_DIR}/status.txt")
    if status.strip() != "OK":
        raise AdbError(f"手机壁纸导出失败：{status or '没有状态文件'}。请打开伴侣应用并授予权限。")
    with tempfile.TemporaryDirectory(prefix="wallpaper_monet_") as directory:
        local = Path(directory) / "wallpaper.png"
        adb._exec("pull", f"{REMOTE_DIR}/wallpaper.png", str(local), timeout=120)
        return open_image(local)
