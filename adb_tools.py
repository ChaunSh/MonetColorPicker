"""ADB operations. No root required for the attempted secure-settings write.

A successful settings write is NOT proof of a visible HyperOS/MIUI theme change.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import json
import ipaddress
import re
import shlex
import shutil
import subprocess

SETTINGS_KEY = "theme_customization_overlay_packages"
PALETTE_KEY = "android.theme.customization.system_palette"
STYLE_KEY = "android.theme.customization.theme_style"
BACKUP_DIR = Path.home() / ".wallpaper_monet_adb" / "backups"


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class Device:
    serial: str
    status: str


class AdbClient:
    def __init__(self, binary: str = "adb"):
        self.binary = binary
        self.serial = ""

    def _exec(self, *args: str, timeout: int = 18, use_serial: bool = True) -> str:
        exe = shutil.which(self.binary)
        if not exe:
            raise AdbError("未找到 adb。请安装 Android Platform Tools，或在界面中指定 adb.exe 路径。")
        cmd = [exe]
        if use_serial and self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=timeout,
                                    shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as err:
            raise AdbError("ADB 命令超时，请检查设备授权与连接。") from err
        except OSError as err:
            raise AdbError(f"执行 ADB 失败：{err}") from err
        if result.returncode != 0:
            raise AdbError((result.stderr or result.stdout or f"ADB exit {result.returncode}").strip())
        return result.stdout.strip()

    def shell(self, command: str) -> str:
        # A single shell argument prevents Windows command-processor escaping; the
        # remote command itself is escaped with POSIX shlex.quote for JSON values.
        return self._exec("shell", command)

    def devices(self) -> list[Device]:
        out = self._exec("devices", "-l", use_serial=False)
        devices = []
        for line in out.splitlines()[1:]:
            columns = line.strip().split()
            if len(columns) >= 2:
                devices.append(Device(columns[0], columns[1]))
        return devices

    def pair(self, address: str, code: str) -> str:
        address = validate_wireless_address(address)
        if not re.fullmatch(r"[0-9]{6}", code):
            raise AdbError("配对码应为六位数字。")
        out = self._exec("pair", address, code, timeout=30, use_serial=False)
        if "successfully paired" not in out.lower():
            raise AdbError(out or "ADB 未确认配对成功。")
        return out

    def connect(self, address: str) -> str:
        address = validate_wireless_address(address)
        out = self._exec("connect", address, timeout=30, use_serial=False)
        if not (out.lower().startswith("connected to ") or
                out.lower().startswith("already connected to ")):
            raise AdbError(out or "ADB 未确认连接成功。")
        return out

    def screen_size(self) -> tuple[int, int]:
        out = self.shell("wm size")
        # An overridden (current) size takes precedence over the physical screen size.
        matches = re.findall(r"(?:Override|Physical) size:\s*(\d+)\s*x\s*(\d+)", out)
        if not matches:
            raise AdbError(f"无法解析屏幕分辨率：{out}")
        w, h = map(int, matches[-1])
        return min(w, h), max(w, h)

    def device_info(self) -> str:
        manufacturer = self.shell("getprop ro.product.manufacturer")
        model = self.shell("getprop ro.product.model")
        version = self.shell("getprop ro.build.version.release")
        return f"{manufacturer} {model} (Android {version})"

    def get_setting(self) -> str | None:
        raw = self.shell(f"settings get secure {SETTINGS_KEY}")
        return None if raw in ("", "null") else raw

    def put_setting(self, raw: str | None) -> None:
        if raw is None:
            self.shell(f"settings delete secure {SETTINGS_KEY}")
        else:
            self.shell(f"settings put secure {SETTINGS_KEY} {shlex.quote(raw)}")


def validate_wireless_address(address: str) -> str:
    """Require an explicit host and port, including brackets around IPv6."""
    address = address.strip()
    if address.startswith("["):
        match = re.fullmatch(r"\[([^\]]+)\]:([0-9]+)", address)
        if not match:
            raise AdbError("地址应为 IP:端口，IPv6 地址请使用 [地址]:端口。")
        try:
            ipaddress.IPv6Address(match.group(1))
        except ValueError as err:
            raise AdbError("IPv6 地址无效。") from err
        port = match.group(2)
    else:
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9.-]*):([0-9]+)", address)
        if not match:
            raise AdbError("地址应为 IP:端口，例如 192.168.1.2:37123。")
        port = match.group(2)
    if not 1 <= int(port) <= 65535:
        raise AdbError("端口应在 1～65535 之间。")
    return address


def build_theme_payload(previous: str | None, seed: int, style: str) -> str:
    """Keep unrelated existing theme keys and override only the intended palette."""
    old: dict = {}
    if previous:
        try:
            parsed = json.loads(previous)
            if isinstance(parsed, dict):
                old = parsed
        except ValueError:
            # Still back up the malformed original setting; don't merge malformed JSON.
            pass
    old[PALETTE_KEY] = f"{seed & 0xFFFFFF:06X}"
    old[STYLE_KEY] = style
    old["android.theme.customization.color_source"] = "preset"
    old["android.theme.customization.accent_color"] = f"{seed & 0xFFFFFF:06X}"  # Legacy Android 12
    old.pop("android.theme.customization.color_index", None)
    old["_applied_timestamp"] = round(datetime.now().timestamp() * 1000)
    return json.dumps(old, separators=(",", ":"), ensure_ascii=True)


def create_backup(serial: str, previous: str | None, replacement: str,
                  backup_dir: Path = BACKUP_DIR) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_serial = re.sub(r"[^A-Za-z0-9_.-]", "_", serial)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = backup_dir / f"{safe_serial}_{timestamp}.json"
    data = {
        "device_serial": serial,
        "created": datetime.now().isoformat(timespec="seconds"),
        "settings_key": SETTINGS_KEY,
        "previous_raw_value": previous,
        "new_raw_value": replacement,
    }
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def apply_theme(adb: AdbClient, seed: int, style: str) -> tuple[Path, bool, str]:
    if not adb.serial:
        raise AdbError("请先选择一台已授权的 Android 设备。")
    previous = adb.get_setting()
    payload = build_theme_payload(previous, seed, style)
    backup = create_backup(adb.serial, previous, payload)
    adb.put_setting(payload)
    readback = adb.get_setting()
    try:
        confirmed = json.loads(readback or "null") == json.loads(payload)
    except ValueError:
        confirmed = False
    return backup, confirmed, readback or "null"


def restore_theme(adb: AdbClient, backup_file: Path) -> bool:
    backup = json.loads(backup_file.read_text(encoding="utf-8"))
    if backup.get("device_serial") != adb.serial:
        raise AdbError("备份对应的设备序列号与当前选择的设备不同，已取消恢复。")
    previous = backup["previous_raw_value"]
    adb.put_setting(previous)
    return adb.get_setting() == previous


def find_latest_backup(serial: str, backup_dir: Path = BACKUP_DIR) -> Path | None:
    safe_serial = re.sub(r"[^A-Za-z0-9_.-]", "_", serial)
    backups = sorted(backup_dir.glob(f"{safe_serial}_*.json"), reverse=True) if backup_dir.is_dir() else []
    return backups[0] if backups else None
