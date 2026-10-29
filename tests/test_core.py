from PIL import Image
import json
from pathlib import Path
import pytest

from core import crop_box, processed_image, save_image, open_image, seed_hex, palette_document
from adb_tools import AdbClient, build_theme_payload, create_backup, restore_theme, find_latest_backup


def test_crop_aspect_and_center():
    box = crop_box((3200, 2000), (1080, 2400))
    w, h = box[2] - box[0], box[3] - box[1]
    assert abs(w / h - 1080 / 2400) < .001
    assert h == 2000
    assert box[0] > 0


def test_crop_zoom_drag_clamp():
    normal = crop_box((1000, 1400), (1080, 2400), zoom=1)
    close = crop_box((1000, 1400), (1080, 2400), zoom=2, center=(0, 1))
    assert close[2] - close[0] < normal[2] - normal[0]
    assert close[0] == 0
    assert close[3] == 1400


def test_crop_export_resize_and_uncropped():
    img = Image.new("RGB", (1000, 700), "red")
    cropped = processed_image(img, crop=True, target_size=(120, 240), zoom=1.0, center=(.5, .5), resize=True)
    assert cropped.size == (120, 240)
    uncropped = processed_image(img, crop=False, target_size=(120, 240), zoom=3.0, center=(0, 0), resize=True)
    assert uncropped.size == img.size
    assert uncropped is not img


def test_image_roundtrip(tmp_path):
    img = Image.new("RGB", (23, 44), "#77AA13")
    path = tmp_path / "wall.png"
    save_image(img, path)
    assert open_image(path).size == (23, 44)
    assert open_image(path).getpixel((0, 0)) == (0x77, 0xAA, 0x13)
    with pytest.raises(ValueError):
        save_image(img, tmp_path / "bad.xyz")


def test_payload_keeps_unknown_keys():
    prev = json.dumps({"some_vendor_key": "preserved", "android.theme.customization.color_index": "2"})
    payload = json.loads(build_theme_payload(prev, 0xFFAA8800, "TONAL_SPOT"))
    assert payload["some_vendor_key"] == "preserved"
    assert payload["android.theme.customization.system_palette"] == "AA8800"
    assert payload["android.theme.customization.theme_style"] == "TONAL_SPOT"
    assert "android.theme.customization.color_index" not in payload


def test_backup_restore(tmp_path):
    serial = "xyz:5555"
    content = '{"foo":"bar"}'
    p = create_backup(serial, content, '{"foo":"new"}', tmp_path)
    assert find_latest_backup(serial, tmp_path) == p
    class FakeAdb:
        serial = "xyz:5555"
        def __init__(self): self.raw = '{"foo":"new"}'
        def put_setting(self, val): self.raw = val
        def get_setting(self): return self.raw
    adb = FakeAdb()
    assert restore_theme(adb, p)
    assert adb.raw == content
    adb.serial = "not_this_one"
    with pytest.raises(Exception, match="序列号"):
        restore_theme(adb, p)


def test_palette_json():
    data = json.loads(palette_document(0xFF3377AB, "TONAL_SPOT", {"accent1": {"system_accent1_0": "#FFFFFF"}}, "image.png", True))
    assert data["seed_color"] == "#3377AB"
    assert data["cropped_for_extraction"] is True


def test_apply_theme_readback_and_backup(tmp_path, monkeypatch):
    import adb_tools
    class FakeAdb:
        serial = "serial123"
        def __init__(self): self.value = '{"vendor":"a"}'
        def get_setting(self): return self.value
        def put_setting(self, val): self.value = val
    adb = FakeAdb()
    original_backup = adb_tools.create_backup
    monkeypatch.setattr(adb_tools, "create_backup", lambda s, p, r: original_backup(s, p, r, tmp_path))
    backup, confirmed, readback = adb_tools.apply_theme(adb, 0xFFCC3366, "VIBRANT")
    assert confirmed
    assert json.loads(readback)["vendor"] == "a"
    assert json.loads(readback)["android.theme.customization.system_palette"] == "CC3366"
    assert restore_theme(adb, backup)
    assert adb.value == '{"vendor":"a"}'


def test_shell_setting_escapes_json(monkeypatch):
    import shlex
    cli = AdbClient()
    record = {}
    def fake_exec(*args, **kw):
        record["args"] = args
        return ""
    monkeypatch.setattr(cli, "_exec", fake_exec)
    cli.put_setting('{"x":"a b", "y":"q\'"}')
    assert record["args"][0] == "shell"
    assert shlex.split(record["args"][1])[-1] == '{"x":"a b", "y":"q\'"}'
