"""Pure image and color utilities for Wallpaper Monet ADB Studio."""
from __future__ import annotations

from pathlib import Path
import json

from PIL import Image, ImageOps

FALLBACK_SEED = 0xFF1B6EF3
STYLES = (
    "TONAL_SPOT", "VIBRANT", "EXPRESSIVE", "SPRITZ", "RAINBOW",
    "FRUIT_SALAD", "MONOCHROMATIC",
)
TONE_INDICES = (0, 10, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000)
PALETTE_NAMES = (
    ("accent1", "主强调色"), ("accent2", "次强调色"),
    ("accent3", "第三强调色"), ("neutral1", "中性色 1"),
    ("neutral2", "中性色 2"),
)


def open_image(path: str | Path) -> Image.Image:
    """Honor EXIF orientation and flatten transparency to white."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA") or "transparency" in im.info:
            rgba = im.convert("RGBA")
            base = Image.new("RGBA", rgba.size, "white")
            base.alpha_composite(rgba)
            return base.convert("RGB")
        return im.convert("RGB")


def valid_dimensions(width: int, height: int) -> tuple[int, int]:
    width, height = int(width), int(height)
    if not (1 <= width <= 16384 and 1 <= height <= 16384):
        raise ValueError("屏幕宽度和高度应在 1～16384 像素之间。")
    return width, height


def crop_box(image_size: tuple[int, int], target_size: tuple[int, int],
             zoom: float = 1.0, center: tuple[float, float] = (0.5, 0.5)) -> tuple[int, int, int, int]:
    """Aspect-locked crop, with zoom=1 selecting the largest possible rectangle."""
    iw, ih = image_size
    tw, th = valid_dimensions(*target_size)
    if iw < 1 or ih < 1:
        raise ValueError("源图片尺寸无效")
    zoom = max(1.0, min(8.0, float(zoom)))
    scale = min(iw / tw, ih / th) / zoom
    cw = max(1, min(iw, round(tw * scale)))
    ch = max(1, min(ih, round(th * scale)))
    cx, cy = center
    left = round(max(0, min(1, cx)) * iw - cw / 2)
    top = round(max(0, min(1, cy)) * ih - ch / 2)
    left = max(0, min(iw - cw, left))
    top = max(0, min(ih - ch, top))
    return (left, top, left + cw, top + ch)


def processed_image(image: Image.Image, *, crop: bool, target_size: tuple[int, int],
                    zoom: float, center: tuple[float, float], resize: bool) -> Image.Image:
    if not crop:
        return image.copy()
    box = crop_box(image.size, target_size, zoom, center)
    result = image.crop(box)
    if resize and result.size != target_size:
        result = result.resize(target_size, Image.Resampling.LANCZOS)
    return result


def save_image(image: Image.Image, path: str | Path) -> None:
    path = Path(path)
    extension = path.suffix.lower()
    if extension in (".jpg", ".jpeg"):
        image.convert("RGB").save(path, format="JPEG", quality=96, subsampling=0)
    elif extension == ".png":
        image.save(path, format="PNG", optimize=True)
    elif extension == ".webp":
        image.save(path, format="WEBP", quality=97)
    else:
        raise ValueError("请导出为 PNG、JPG 或 WEBP")


def seed_hex(seed: int) -> str:
    return f"#{seed & 0xFFFFFF:06X}"


def extract_seed_candidates(image: Image.Image, max_size: int = 520) -> list[int]:
    """Celebi quantization and Material You Score; return ranked opaque ARGB colors."""
    from materialyoucolor.quantize import ImageQuantizeCelebi
    from materialyoucolor.score.score import Score
    import tempfile
    small = image.copy().convert("RGB")
    small.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    # The package's C++ backend accepts a filesystem path; keep it portable on Windows.
    with tempfile.TemporaryDirectory(prefix="monet_extract_") as folder:
        path = Path(folder) / "sampling.png"
        small.save(path, format="PNG")
        populations = ImageQuantizeCelebi(str(path), 1, 128)
    colors = Score.score(populations)
    if not colors:
        colors = [FALLBACK_SEED]
    return [int(c) | 0xFF000000 for c in colors[:8]]


def generate_palette(seed: int, style: str = "TONAL_SPOT") -> dict[str, dict[str, str]]:
    """AOSP/Android-12-style tonal palettes, with 65 color resources."""
    if style not in STYLES:
        raise ValueError(f"不支持的样式: {style}")
    from materialyoucolor.hct import Hct
    from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot
    from materialyoucolor.scheme.scheme_vibrant import SchemeVibrant
    from materialyoucolor.scheme.scheme_expressive import SchemeExpressive
    from materialyoucolor.scheme.scheme_neutral import SchemeNeutral
    from materialyoucolor.scheme.scheme_rainbow import SchemeRainbow
    from materialyoucolor.scheme.scheme_fruit_salad import SchemeFruitSalad
    from materialyoucolor.scheme.scheme_monochrome import SchemeMonochrome
    classes = {
        "TONAL_SPOT": SchemeTonalSpot,
        "VIBRANT": SchemeVibrant,
        "EXPRESSIVE": SchemeExpressive,
        "SPRITZ": SchemeNeutral,  # Closest supported library variant to AOSP SPRITZ
        "RAINBOW": SchemeRainbow,
        "FRUIT_SALAD": SchemeFruitSalad,
        "MONOCHROMATIC": SchemeMonochrome,
    }
    scheme = classes[style](Hct.from_int(seed), False, 0.0, spec_version="2021")
    result: dict[str, dict[str, str]] = {}
    pals = {
        "accent1": scheme.primary_palette,
        "accent2": scheme.secondary_palette,
        "accent3": scheme.tertiary_palette,
        "neutral1": scheme.neutral_palette,
        "neutral2": scheme.neutral_variant_palette,
    }
    for name, palette in pals.items():
        result[name] = {
            f"system_{name}_{index}": seed_hex(palette.tone(100 - index / 10))
            for index in TONE_INDICES
        }
    return result


def palette_document(seed: int, style: str, colors: dict[str, dict[str, str]],
                     image_name: str, cropped: bool) -> str:
    return json.dumps({
        "source_image": image_name,
        "cropped_for_extraction": cropped,
        "seed_color": seed_hex(seed),
        "theme_style": style,
        "note": "本文件是本地预览色阶；ADB 实际写入的是系统源色和主题样式，而非逐项写入这些色值。",
        "tonal_palettes": colors,
    }, ensure_ascii=False, indent=2)
