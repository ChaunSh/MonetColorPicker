"""Wallpaper Monet ADB Studio — Windows desktop app (Tkinter, no root).

Launch with run_windows.bat. The app cannot guarantee vendor SystemUI will honor
AOSP's secure theme setting; it verifies settings readback and offers restore.
"""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from core import (STYLES, PALETTE_NAMES, TONE_INDICES, crop_box, extract_seed_candidates,
                  generate_palette, open_image, palette_document, processed_image,
                  save_image, seed_hex, valid_dimensions)
from adb_tools import (AdbClient, AdbError, apply_theme, find_latest_backup, restore_theme)
from companion import fetch_wallpaper

BG = "#0B1220"
PANEL = "#17243A"
PANEL_ALT = "#263650"
TEXT = "#EDF4FA"
MUTED = "#9FB0C1"
ACCENT = "#78D5EC"
BORDER = "#2C4053"
ERROR = "#F6A6A6"



class MonetApp(tk.Tk):
    def __init__(self) -> None:
        # Declare DPI awareness before Tk creates its first native window.
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
        super().__init__()
        self.title("Wallpaper Monet ADB Studio · 壁纸取色与写入")
        # Tk font sizes use points; canvas coordinates and window sizes use pixels.
        self.dpi_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(round(1210 * self.dpi_scale), int(screen_w * .95))
        height = min(round(790 * self.dpi_scale), int(screen_h * .90))
        self.geometry(f"{width}x{height}")
        self.minsize(min(round(780 * self.dpi_scale), width),
                     min(round(540 * self.dpi_scale), height))
        self.configure(bg=BG)
        self.image: Image.Image | None = None
        self.image_path: Path | None = None
        self.preview_photo = None
        self.preview_geometry = (0.0, 0.0, 1.0)  # left, top, scale
        self.crop_center = [0.5, 0.5]
        self.drag_origin: tuple[int, int, list[float]] | None = None
        self.candidates: list[int] = []
        self.selected_seed: int | None = None
        self.palette: dict[str, dict[str, str]] = {}
        self.palette_current = False
        self._generation = 0
        self.processing = False
        self.adb = AdbClient()
        self.device_status: dict[str, str] = {}
        self.event_queue: queue.Queue = queue.Queue()
        self._resize_timer = None
        self._setup_style()
        self._build_ui()
        self.after(120, self._drain_events)
        self.after(500, self.refresh_devices)

    def _setup_style(self) -> None:
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        s.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Microsoft YaHei UI", 10))
        s.configure("Hint.TLabel", background=PANEL, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        s.configure("Title.TLabel", background=BG, foreground=TEXT,
                    font=("Microsoft YaHei UI", 19, "bold"))
        s.configure("Section.TLabel", background=PANEL, foreground=TEXT,
                    font=("Microsoft YaHei UI", 12, "bold"))
        s.configure("TCheckbutton", background=PANEL, foreground=TEXT,
                    font=("Microsoft YaHei UI", 9))
        s.map("TCheckbutton", background=[("active", PANEL)], foreground=[("active", TEXT)])
        s.configure("TButton", padding=(9, 7), background=PANEL_ALT, foreground=TEXT,
                    borderwidth=0, relief="flat", font=("Microsoft YaHei UI", 9))
        s.map("TButton", background=[("active", "#2C435B"), ("disabled", "#233244")],
              foreground=[("disabled", "#7B8B99")])
        s.configure("Accent.TButton", background="#087C98", foreground="white",
                    padding=(10, 9), font=("Microsoft YaHei UI", 10, "bold"))
        s.map("Accent.TButton", background=[("active", "#1097B5")])
        s.configure("TEntry", fieldbackground="#243448", foreground=TEXT, padding=5)
        s.configure("TCombobox", fieldbackground="#243448", background="#243448",
                    foreground=TEXT, padding=5)
        s.map("TCombobox", fieldbackground=[("readonly", "#243448")],
              foreground=[("readonly", TEXT)])
        s.configure("Horizontal.TScale", background=PANEL, troughcolor="#2A3B4C")

    def _panel(self, parent, row: int, column: int, sticky="nsew", **kwargs) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        frame.grid(row=row, column=column, sticky=sticky, **kwargs)
        return frame

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(22, 16, 22, 8))
        header.pack(fill="x")
        ttk.Label(header, text="Wallpaper Monet ADB Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="裁切壁纸  /  提取 Material You 主色  /  预览 65 色  /  无 Root ADB 写入（取决于系统支持）",
                  foreground=MUTED).pack(anchor="w", pady=(3, 0))

        # Scroll when the available screen cannot accommodate the controls at
        # the current display scale (e.g. a laptop at 200% scaling).
        viewport = ttk.Frame(self)
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        horizontal = ttk.Scrollbar(viewport, orient="horizontal", command=canvas.xview)
        scrollbar.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        body = ttk.Frame(canvas, padding=(16, 8, 16, 13))
        body_window = canvas.create_window(0, 0, window=body, anchor="nw")
        def resize_body(event):
            canvas.itemconfigure(body_window, width=max(event.width, round(960 * self.dpi_scale)),
                                 height=max(event.height, body.winfo_reqheight()))
            canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.bind("<Configure>", resize_body)
        def update_scrollregion(event):
            desired = max(canvas.winfo_height(), body.winfo_reqheight())
            if int(float(canvas.itemcget(body_window, "height"))) != desired:
                canvas.itemconfigure(body_window, height=desired)
            canvas.configure(scrollregion=canvas.bbox("all"))
        body.bind("<Configure>", update_scrollregion)
        body.columnconfigure(0, weight=7, uniform="cols")
        body.columnconfigure(1, weight=5, uniform="cols")
        body.rowconfigure(0, weight=1)

        left = self._panel(body, 0, 0, padx=(0, 8))
        right = self._panel(body, 0, 1, padx=(8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)

        # Left: image input, canvas and crop controls.
        top = ttk.Frame(left, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="01  壁纸和裁切", style="Section.TLabel").pack(side="left")
        ttk.Button(top, text="选择图片…", command=self.choose_image).pack(side="right")
        self.file_caption = tk.StringVar(value="尚未选择图片（支持 PNG / JPG / WEBP / BMP / TIFF）")
        ttk.Label(left, textvariable=self.file_caption, style="Hint.TLabel").grid(row=1, column=0, sticky="ew", pady=(8, 7))

        preview_wrap = tk.Frame(left, bg="#0B1119", highlightbackground=BORDER,
                                highlightthickness=1)
        preview_wrap.grid(row=2, column=0, sticky="nsew")
        self.preview = tk.Canvas(preview_wrap, bg="#0B1119", highlightthickness=0, cursor="fleur")
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", self._schedule_redraw)
        self.preview.bind("<ButtonPress-1>", self._start_drag)
        self.preview.bind("<B1-Motion>", self._drag)
        self.preview.bind("<ButtonRelease-1>", lambda _: setattr(self, "drag_origin", None))
        self.preview.bind("<MouseWheel>", self._wheel_zoom)
        self.preview.bind("<Button-4>", lambda _: self._nudge_zoom(-0.1))
        self.preview.bind("<Button-5>", lambda _: self._nudge_zoom(+0.1))

        crop_controls = ttk.Frame(left, style="Panel.TFrame")
        crop_controls.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.crop_var = tk.BooleanVar(value=True)
        self.resize_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(crop_controls, text="按屏幕比例裁切", variable=self.crop_var,
                        command=self._crop_changed).pack(side="left")
        ttk.Checkbutton(crop_controls, text="导出时缩放至屏幕分辨率", variable=self.resize_var,
                        command=self._crop_changed).pack(side="right")

        sizes = ttk.Frame(left, style="Panel.TFrame")
        sizes.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(sizes, text="目标尺寸", style="Panel.TLabel").pack(side="left")
        self.width_var = tk.StringVar(value="1080")
        self.height_var = tk.StringVar(value="2400")
        ttk.Entry(sizes, textvariable=self.width_var, width=7).pack(side="left", padx=(11, 5))
        ttk.Label(sizes, text="×", style="Panel.TLabel").pack(side="left")
        ttk.Entry(sizes, textvariable=self.height_var, width=7).pack(side="left", padx=(5, 11))
        ttk.Button(sizes, text="从手机读取", command=self.read_screen_size).pack(side="left")
        for variable in (self.width_var, self.height_var):
            variable.trace_add("write", lambda *_: self._crop_changed())

        zoom_row = ttk.Frame(left, style="Panel.TFrame")
        zoom_row.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        zoom_row.columnconfigure(1, weight=1)
        ttk.Label(zoom_row, text="裁切缩放", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.zoom_var = tk.DoubleVar(value=1.0)
        self.zoom_scale = ttk.Scale(zoom_row, from_=1.0, to=5.0, variable=self.zoom_var,
                                    command=lambda _: self._crop_changed())
        self.zoom_scale.grid(row=0, column=1, sticky="ew")
        self.zoom_label = ttk.Label(zoom_row, text="1.00×", style="Hint.TLabel", width=7)
        self.zoom_label.grid(row=0, column=2, padx=(7, 0))
        ttk.Label(left, text="拖动裁切框调整位置；滚轮调整范围。取消裁切后，计算基于整张原图。",
                  style="Hint.TLabel").grid(row=6, column=0, sticky="w", pady=(8, 0))
        actions = ttk.Frame(left, style="Panel.TFrame")
        actions.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(actions, text="导出图片…", command=self.export_image).pack(side="left", padx=(0, 9))
        ttk.Button(actions, text="重新居中", command=self.reset_crop).pack(side="left")
        self.source_caption = ttk.Label(actions, text="", style="Hint.TLabel")
        self.source_caption.pack(side="right")

        # Right: palette selection, preview, ADB.
        ttk.Label(right, text="02  Monet 动态配色", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        settings = ttk.Frame(right, style="Panel.TFrame")
        settings.grid(row=1, column=0, sticky="ew", pady=(9, 0))
        ttk.Label(settings, text="变体", style="Panel.TLabel").pack(side="left")
        self.style_var = tk.StringVar(value="TONAL_SPOT")
        self.style_combo = ttk.Combobox(settings, state="readonly", textvariable=self.style_var,
                                        values=STYLES, width=16)
        self.style_combo.pack(side="left", padx=(8, 8))
        self.style_combo.bind("<<ComboboxSelected>>", lambda _: self._style_changed())
        self.calc_button = ttk.Button(settings, text="分析图片颜色", style="Accent.TButton", command=self.analyze)
        self.calc_button.pack(side="right")

        self.seed_caption = tk.StringVar(value="主色：未计算")
        ttk.Label(right, textvariable=self.seed_caption, style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=(11, 3))
        self.candidate_canvas = tk.Canvas(right, height=round(54 * self.dpi_scale), bg=PANEL, highlightthickness=0)
        self.candidate_canvas.grid(row=3, column=0, sticky="ew")
        self.candidate_canvas.bind("<Button-1>", self._candidate_click)
        self.candidate_canvas.bind("<Configure>", lambda _: self._draw_candidates())
        self.palette_canvas = tk.Canvas(right, bg=PANEL, height=round(260 * self.dpi_scale), highlightthickness=0)
        self.palette_canvas.grid(row=4, column=0, sticky="nsew", pady=(8, 4))
        self.palette_canvas.bind("<Configure>", lambda _: self._draw_palette())
        self.palette_canvas.bind("<Button-1>", self._palette_click)
        ttk.Button(right, text="导出 65 色调色板 JSON…", command=self.export_palette).grid(row=5, column=0, sticky="w", pady=(0, 10))

        sep = ttk.Separator(right)
        sep.grid(row=6, column=0, sticky="ew", pady=(1, 11))
        ttk.Label(right, text="03  Android / ADB", style="Section.TLabel").grid(row=7, column=0, sticky="w")

        adb_row = ttk.Frame(right, style="Panel.TFrame")
        adb_row.grid(row=8, column=0, sticky="ew", pady=(9, 5))
        adb_row.columnconfigure(0, weight=1)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(adb_row, state="readonly", textvariable=self.device_var)
        self.device_combo.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.device_combo.bind("<<ComboboxSelected>>", self._select_device)
        ttk.Button(adb_row, text="刷新设备", command=self.refresh_devices).grid(row=0, column=1)
        ttk.Button(adb_row, text="无线调试…", command=self.wireless_dialog).grid(row=0, column=2, padx=(7, 0))
        path_row = ttk.Frame(right, style="Panel.TFrame")
        path_row.grid(row=9, column=0, sticky="ew")
        path_row.columnconfigure(1, weight=1)
        ttk.Label(path_row, text="ADB", style="Hint.TLabel").grid(row=0, column=0, padx=(0, 7))
        self.adb_var = tk.StringVar(value="adb")
        ttk.Entry(path_row, textvariable=self.adb_var).grid(row=0, column=1, sticky="ew", padx=(0, 7))
        ttk.Button(path_row, text="定位…", command=self.choose_adb).grid(row=0, column=2)

        adb_actions = ttk.Frame(right, style="Panel.TFrame")
        adb_actions.grid(row=10, column=0, sticky="ew", pady=(10, 5))
        ttk.Button(adb_actions, text="写入选定主色", style="Accent.TButton", command=self.write_to_android).pack(side="left", padx=(0, 7))
        ttk.Button(adb_actions, text="恢复最近备份", command=self.restore_last).pack(side="left")
        ttk.Button(adb_actions, text="读取手机壁纸", command=self.import_wallpaper).pack(side="left", padx=(7, 0))
        ttk.Label(right, text="写入前自动备份。写入后的界面效果取决于 ROM 是否支持 AOSP Monet。",
                  style="Hint.TLabel", wraplength=430).grid(row=11, column=0, sticky="w", pady=(2, 5))
        self.log = tk.Text(right, height=4, bg="#101A27", fg="#C9E2E9", relief="flat",
                           highlightthickness=1, highlightbackground=BORDER,
                           wrap="word", padx=10, pady=8, font=("Consolas", 9), state="disabled")
        self.log.grid(row=12, column=0, sticky="ew", pady=(4, 0))
        self._log("选择壁纸图片，调整裁切框，再点击“分析图片颜色”。")
        self._draw_blank()

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _run_async(self, worker, success, label: str):
        def run():
            try:
                result = worker()
                self.event_queue.put((success, result, None, label))
            except Exception as exc:
                self.event_queue.put((None, None, exc, label))
        threading.Thread(target=run, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                callback, result, error, label = self.event_queue.get_nowait()
                if error:
                    self.processing = False
                    self.calc_button.configure(state="normal")
                    self._log(f"[失败] {label}：{error}")
                    messagebox.showerror(label, str(error))
                elif callback:
                    callback(result)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def import_wallpaper(self):
        if not self._authorized():
            return
        adb = self.adb
        def done(image):
            self.image = image
            self.image_path = Path("phone_wallpaper.png")
            self._thumb_cache_key = None
            self.file_caption.set(f"手机壁纸  ·  {image.width} × {image.height} px")
            self.reset_crop()
            self._invalidate_palette()
            self._log("已从安卓伴侣应用读取壁纸。")
        self._run_async(lambda: fetch_wallpaper(adb), done, "读取手机壁纸")

    def choose_image(self):
        path = filedialog.askopenfilename(
            title="选择壁纸图片", filetypes=[
                ("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("所有文件", "*.*")])
        if not path:
            return
        try:
            image = open_image(path)
        except Exception as exc:
            messagebox.showerror("图片读取失败", str(exc))
            return
        self.image = image
        self.image_path = Path(path)
        self._thumb_cache_key = None
        self.file_caption.set(f"{self.image_path.name}  ·  {image.width} × {image.height} px")
        self.reset_crop()
        self._invalidate_palette()
        self._log(f"已读取图片：{self.image_path.name}")

    def _target(self):
        return valid_dimensions(int(self.width_var.get()), int(self.height_var.get()))

    def _get_crop(self):
        assert self.image is not None
        return crop_box(self.image.size, self._target(), self.zoom_var.get(), tuple(self.crop_center))

    def _current_processed(self):
        if self.image is None:
            raise ValueError("请先选择图片。")
        return processed_image(self.image, crop=self.crop_var.get(), target_size=self._target(),
                               zoom=self.zoom_var.get(), center=tuple(self.crop_center),
                               resize=self.resize_var.get())

    def _invalidate_palette(self):
        self._generation += 1
        self.palette_current = False
        self.palette = {}
        self.candidates = []
        self.selected_seed = None
        self.seed_caption.set("主色：未计算 / 裁切已变化")
        self._draw_candidates()
        self._draw_palette()

    def _crop_changed(self):
        self.zoom_label.configure(text=f"{self.zoom_var.get():.2f}×")
        self.source_caption.configure(text="裁切模式" if self.crop_var.get() else "整图模式")
        if self.image:
            self._invalidate_palette()
        self._schedule_redraw()

    def reset_crop(self):
        self.crop_center = [0.5, 0.5]
        self.zoom_var.set(1.0)
        self._crop_changed()

    def _schedule_redraw(self, _event=None):
        if self._resize_timer is not None:
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(35, self._draw_preview)

    def _draw_blank(self):
        self.preview.delete("all")
        w, h = max(self.preview.winfo_width(), 400), max(self.preview.winfo_height(), 220)
        self.preview.create_text(w / 2, h / 2 - 10, text="选择一张壁纸图片以开始", fill=MUTED,
                                 font=("Microsoft YaHei UI", 14, "bold"))
        self.preview.create_text(w / 2, h / 2 + 20, text="支持自由移动 / 等比例缩放裁切框", fill="#687B8B")

    def _draw_preview(self):
        self._resize_timer = None
        if not self.image:
            self._draw_blank()
            return
        c = self.preview
        c.delete("all")
        w, h = max(c.winfo_width(), 1), max(c.winfo_height(), 1)
        iw, ih = self.image.size
        scale = min((w - 35) / iw, (h - 30) / ih)
        if scale <= 0:
            return
        pw, ph = max(1, round(iw * scale)), max(1, round(ih * scale))
        x0, y0 = (w - pw) / 2, (h - ph) / 2
        cache_key = (id(self.image), pw, ph)
        if getattr(self, "_thumb_cache_key", None) != cache_key:
            thumb = self.image.resize((pw, ph), Image.Resampling.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(thumb)
            self._thumb_cache_key = cache_key
        c.create_image(x0, y0, image=self.preview_photo, anchor="nw")
        self.preview_geometry = (x0, y0, pw / iw)
        if self.crop_var.get():
            try:
                l, t, r, b = self._get_crop()
            except (ValueError, TypeError):
                c.create_text(12, 14, anchor="nw", fill=ERROR, text="请输入有效的目标分辨率")
                return
            x1, y1 = x0 + l * pw / iw, y0 + t * ph / ih
            x2, y2 = x0 + r * pw / iw, y0 + b * ph / ih
            # Four darkened regions outside the cropping rectangle.
            for rect in ((x0, y0, x0 + pw, y1), (x0, y2, x0 + pw, y0 + ph),
                         (x0, y1, x1, y2), (x2, y1, x0 + pw, y2)):
                c.create_rectangle(*rect, fill="#09131B", stipple="gray50", outline="")
            c.create_rectangle(x1, y1, x2, y2, outline=ACCENT, width=2)
            for i in (1, 2):
                xx = x1 + (x2 - x1) * i / 3
                yy = y1 + (y2 - y1) * i / 3
                c.create_line(xx, y1, xx, y2, fill="#D0F0F7", dash=(3, 4))
                c.create_line(x1, yy, x2, yy, fill="#D0F0F7", dash=(3, 4))
            c.create_text(x1 + 5, y1 + 6, anchor="nw", text=f"{r-l} × {b-t}",
                          fill="#FFFFFF", font=("Consolas", 9, "bold"))
        else:
            c.create_text(x0 + 10, y0 + 10, anchor="nw", text="原图模式 · 不裁切",
                          fill="white", font=("Microsoft YaHei UI", 10, "bold"))

    def _start_drag(self, event):
        if self.image and self.crop_var.get():
            self.drag_origin = (event.x, event.y, self.crop_center[:])

    def _drag(self, event):
        if not self.drag_origin or not self.image:
            return
        x0, y0, initial = self.drag_origin
        _, _, s = self.preview_geometry
        if s <= 0:
            return
        dx = (event.x - x0) / (s * self.image.width)
        dy = (event.y - y0) / (s * self.image.height)
        self.crop_center = [max(0, min(1, initial[0] + dx)), max(0, min(1, initial[1] + dy))]
        self._invalidate_palette()
        self._schedule_redraw()

    def _wheel_zoom(self, event):
        if self.image and self.crop_var.get():
            self._nudge_zoom(-0.12 if event.delta > 0 else 0.12)

    def _nudge_zoom(self, delta):
        self.zoom_var.set(max(1, min(5, self.zoom_var.get() + delta)))
        self._crop_changed()

    def export_image(self):
        if not self.image:
            messagebox.showinfo("需要图片", "请先选择图片。")
            return
        try:
            image = self._current_processed()
        except Exception as exc:
            messagebox.showerror("裁切参数错误", str(exc))
            return
        default = f"{self.image_path.stem}_wallpaper.png" if self.image_path else "wallpaper.png"
        path = filedialog.asksaveasfilename(title="导出壁纸", defaultextension=".png",
                                            initialfile=default, filetypes=[("PNG", "*.png"),
                                            ("JPEG", "*.jpg"), ("WebP", "*.webp")])
        if not path:
            return
        try:
            save_image(image, path)
            self._log(f"已导出 {image.width}×{image.height}：{path}")
            messagebox.showinfo("导出成功", f"已保存：\n{path}\n\n尺寸：{image.width} × {image.height}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def analyze(self):
        if self.processing:
            return
        try:
            image = self._current_processed()
        except Exception as exc:
            messagebox.showerror("无法提取颜色", str(exc))
            return
        self.processing = True
        self.calc_button.configure(state="disabled")
        # Snapshot the style/image state. User changes are tracked through generation.
        self._generation += 1
        generation = self._generation
        self._log("正在进行 Celebi 量化和 Monet 主色评分…")

        def worker():
            return generation, extract_seed_candidates(image)

        def done(result):
            current_generation, candidates = result
            self.processing = False
            self.calc_button.configure(state="normal")
            if current_generation != self._generation:
                self._log("图片已修改，本次分析结果已丢弃；请重新分析。")
                return
            self.candidates = candidates
            self.selected_seed = candidates[0]
            self._make_palette()
            self._log(f"分析完成：{len(candidates)} 个候选主色，默认 {seed_hex(candidates[0])}")

        self._run_async(worker, done, "图片取色")

    def _make_palette(self):
        if self.selected_seed is None:
            return
        try:
            self.palette = generate_palette(self.selected_seed, self.style_var.get())
        except Exception as exc:
            self._log(f"调色板计算失败：{exc}")
            messagebox.showerror("Monet 算法错误", str(exc))
            return
        self.palette_current = True
        self.seed_caption.set(f"主色：{seed_hex(self.selected_seed)}  ·  点击下面的候选色可切换")
        self._draw_candidates()
        self._draw_palette()

    def _style_changed(self):
        if self.selected_seed is not None:
            self._make_palette()

    def _candidate_click(self, event):
        for index, (left, top, right, bottom) in enumerate(getattr(self, "candidate_rects", [])):
            if left <= event.x <= right and top <= event.y <= bottom and index < len(self.candidates):
                self.selected_seed = self.candidates[index]
                self._make_palette()
                return

    def _draw_candidates(self):
        c = self.candidate_canvas
        c.delete("all")
        self.candidate_rects = []
        d = self.dpi_scale
        if not self.candidates:
            c.create_text(8*d, 23*d, text="尚无候选色", anchor="w", fill=MUTED)
            return
        step = min(58*d, max(1, (c.winfo_width() - 10*d) / 6))
        for i, color in enumerate(self.candidates[:6]):
            x0, x1 = 5*d + i*step, 5*d + i*step + step*0.83
            col = seed_hex(color)
            self.candidate_rects.append((x0, 3*d, x1, 48*d))
            active = color == self.selected_seed
            c.create_rectangle(x0, 3*d, x1, 30*d, fill=col, outline="#FFFFFF" if active else BORDER,
                               width=max(1, round((3 if active else 1)*d)))
            c.create_text((x0+x1)/2, 42*d, text=col[1:], fill=TEXT if active else MUTED,
                          font=("Consolas", 8))

    def _draw_palette(self):
        c = self.palette_canvas
        c.delete("all")
        self.palette_rects = []
        d = self.dpi_scale
        if not self.palette:
            c.create_text(8*d, 26*d, text="完成颜色分析后在此预览五组色阶", anchor="w", fill=MUTED)
            return
        cell = max(1, (c.winfo_width() - 16*d) / 13)
        for i, (name, title) in enumerate(PALETTE_NAMES):
            row_y = (20 + i*45)*d
            c.create_text(8*d, row_y-7*d, text=title + f" · {name}", fill=MUTED, anchor="w",
                          font=("Microsoft YaHei UI", 9))
            for j, idx in enumerate(TONE_INDICES):
                left, right = 8*d+j*cell, 8*d+(j+1)*cell
                top, bottom = row_y+7*d, row_y+25*d
                color = self.palette[name][f"system_{name}_{idx}"]
                c.create_rectangle(left, top, right, bottom, fill=color, outline="")
                self.palette_rects.append((left, top, right, bottom, color, f"system_{name}_{idx}"))
        c.create_text(8*d, 253*d, anchor="w", text="点击色块复制 HEX", fill=MUTED,
                      font=("Microsoft YaHei UI", 8))

    def _palette_click(self, event):
        for l, t, r, b, color, name in getattr(self, "palette_rects", []):
            if l <= event.x <= r and t <= event.y <= b:
                self.clipboard_clear()
                self.clipboard_append(color)
                self._log(f"已复制 {name} = {color}")
                return

    def export_palette(self):
        if not self.palette_current or self.selected_seed is None:
            messagebox.showinfo("需要颜色", "请先分析图片颜色。")
            return
        path = filedialog.asksaveasfilename(title="导出 Monet 调色板", defaultextension=".json",
                                            initialfile="monet_palette.json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            out = palette_document(self.selected_seed, self.style_var.get(), self.palette,
                                   self.image_path.name if self.image_path else "", self.crop_var.get())
            Path(path).write_text(out, encoding="utf-8")
            self._log(f"已导出 65 色配色 JSON：{path}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def wireless_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("ADB 无线调试")
        dialog.configure(bg=BG)
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Android 11+：在手机的无线调试中查看配对地址、配对码和连接地址。", wraplength=440).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        pair_addr = tk.StringVar()
        pair_code = tk.StringVar()
        connect_addr = tk.StringVar()
        for row, (label, var) in enumerate((("配对地址 IP:端口", pair_addr), ("六位配对码", pair_code), ("连接地址 IP:端口", connect_addr)), 1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=var, width=30).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
        def run(action):
            address = (pair_addr if action == "pair" else connect_addr).get().strip()
            code = pair_code.get().strip()
            if not address or (action == "pair" and not code):
                messagebox.showwarning("信息不完整", "请输入地址及所需的配对码。", parent=dialog)
                return
            client = AdbClient(self.adb_var.get().strip() or "adb")
            def done(result):
                self._log(result)
                if action == "connect":
                    self.refresh_devices()
            self._run_async(lambda: client.pair(address, code) if action == "pair" else client.connect(address), done, "无线调试")
        ttk.Button(frame, text="配对", command=lambda: run("pair")).grid(row=4, column=0, pady=(12, 0))
        ttk.Button(frame, text="连接", style="Accent.TButton", command=lambda: run("connect")).grid(row=4, column=1, sticky="e", pady=(12, 0))

    def choose_adb(self):
        path = filedialog.askopenfilename(title="定位 Android Debug Bridge", filetypes=[("ADB", "adb.exe adb"), ("所有文件", "*.*")])
        if path:
            self.adb_var.set(path)
            self.refresh_devices()

    def refresh_devices(self):
        path = self.adb_var.get().strip() or "adb"
        def worker():
            adb = AdbClient(path)
            return adb.devices()
        def done(devices):
            previous = self.adb.serial
            self.device_status = {x.serial: x.status for x in devices}
            serials = [x.serial for x in devices]
            self.device_combo["values"] = serials
            if previous in serials:
                serial = previous
            else:
                serial = next((d.serial for d in devices if d.status == "device"), "")
            self.device_var.set(serial)
            self._select_device()
            if devices:
                self._log("ADB 设备：" + ", ".join(f"{d.serial} [{d.status}]" for d in devices))
            else:
                self._log("暂无设备：请连接 USB、开启 USB 调试并授权电脑。")
        self._run_async(worker, done, "ADB 设备扫描")

    def _select_device(self, _event=None):
        self.adb = AdbClient(self.adb_var.get().strip() or "adb")
        self.adb.serial = self.device_var.get().strip()

    def _authorized(self) -> bool:
        self._select_device()
        if not self.adb.serial:
            messagebox.showwarning("未连接手机", "没有选中的 ADB 设备；请检查 USB 调试与授权。")
            return False
        if self.device_status.get(self.adb.serial) != "device":
            messagebox.showwarning("设备未授权", "当前设备状态不是 device。请解锁手机并允许 USB 调试授权。")
            return False
        return True

    def read_screen_size(self):
        if not self._authorized():
            return
        adb = self.adb
        def done(size):
            self.width_var.set(str(size[0]))
            self.height_var.set(str(size[1]))
            self._log(f"已读取屏幕尺寸：{size[0]} × {size[1]}（纵向）")
        self._run_async(adb.screen_size, done, "读取屏幕尺寸")

    def write_to_android(self):
        if self.selected_seed is None or not self.palette_current:
            messagebox.showinfo("需要配色", "请先从当前图片提取 Monet 颜色。")
            return
        if not self._authorized():
            return
        seed = self.selected_seed
        style = self.style_var.get()
        adb = self.adb
        confirm = messagebox.askyesno(
            "确认写入手机", f"设备：{adb.serial}\n主色：{seed_hex(seed)}\n样式：{style}\n\n"
            "写入前将自动备份当前主题设置。\n"
            "HyperOS/MIUI 可能忽略此 AOSP 设置；可能需要重新打开受影响的应用。\n\n继续吗？")
        if not confirm:
            return
        def done(result):
            backup, confirmed, value = result
            self._log(f"已写入；回读{'一致' if confirmed else '不一致'}；备份：{backup}")
            if confirmed:
                messagebox.showinfo("ADB 写入完成", f"ADB Secure Setting 回读验证成功。\n\n"
                                    f"备份文件：\n{backup}\n\n"
                                    "注意：仅证明系统设置已写入，不保证 HyperOS UI 实际应用新色。")
            else:
                messagebox.showwarning("写入未验证", f"写入命令已执行，但设置回读不匹配。\n\n"
                                       f"备份：{backup}\n读取值：{value[:250]}")
        self._run_async(lambda: apply_theme(adb, seed, style), done, "写入 Monet")

    def restore_last(self):
        if not self._authorized():
            return
        adb = self.adb
        backup = find_latest_backup(adb.serial)
        if not backup:
            messagebox.showinfo("没有备份", "当前设备还没有由此工具生成的本地设置备份。")
            return
        if not messagebox.askyesno("恢复主题设置", f"将恢复备份：\n{backup.name}\n\n确认覆盖手机当前设置？"):
            return
        def done(ok):
            self._log(f"备份恢复：{'回读一致' if ok else '回读未匹配'}  {backup.name}")
            if ok:
                messagebox.showinfo("恢复完成", "已恢复备份中的原始设置并通过回读验证。")
            else:
                messagebox.showwarning("无法确认恢复", "恢复命令已执行，但原始设置回读未完全匹配。")
        self._run_async(lambda: restore_theme(adb, backup), done, "恢复原始主题")


if __name__ == "__main__":
    MonetApp().mainloop()
