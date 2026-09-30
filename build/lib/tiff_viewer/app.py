"""Tk desktop application for viewing scientific TIFF files."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from math import hypot
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
import tifffile
from PIL import Image, ImageTk

from .calibration import Calibration, CalibrationStore
from .image_processing import (
    ImageStatistics,
    contrast_limits,
    image_statistics,
    to_display_image,
)


APP_NAME = "TIFF Viewer"
TIFF_TYPES = [("Immagini TIFF", "*.tif *.tiff"), ("Tutti i file", "*")]


class ViewerCanvas(ttk.Frame):
    """A canvas that renders only the visible part of a zoomed image."""

    def __init__(
        self,
        master: tk.Misc,
        zoom_callback=None,
        pixel_callback=None,
        measurement_callback=None,
    ) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(
            self,
            background="#202124",
            highlightthickness=0,
            cursor="fleur",
        )
        self.canvas.pack(fill="both", expand=True)

        self.image: Image.Image | None = None
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.fit_active = True
        self._photo: ImageTk.PhotoImage | None = None
        self._render_job: str | None = None
        self._drag_start: tuple[int, int, float, float] | None = None
        self._zoom_callback = zoom_callback
        self._pixel_callback = pixel_callback
        self._measurement_callback = measurement_callback
        self.measurement_mode = False
        self.measurement_line: tuple[float, float, float, float] | None = None
        self._measurement_start: tuple[float, float] | None = None

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<ButtonPress-1>", self._start_pan)
        self.canvas.bind("<B1-Motion>", self._pan)
        self.canvas.bind("<ButtonRelease-1>", self._stop_pan)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda event: self._zoom_at(event.x, event.y, 1.2))
        self.canvas.bind("<Button-5>", lambda event: self._zoom_at(event.x, event.y, 1 / 1.2))
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _event: self._report_pixel(None, None))

    def set_image(self, image: Image.Image, fit: bool = True) -> None:
        self.image = image
        if fit:
            self.fit_active = True
            self.after_idle(self.fit)
        else:
            self._schedule_render()

    def fit(self) -> None:
        if self.image is None:
            return
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self.scale = min(width / self.image.width, height / self.image.height)
        self.scale = max(0.01, self.scale)
        self.offset_x = (width - self.image.width * self.scale) / 2.0
        self.offset_y = (height - self.image.height * self.scale) / 2.0
        self.fit_active = True
        self._schedule_render()
        self._report_zoom()

    def actual_size(self) -> None:
        if self.image is None:
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.scale = 1.0
        self.offset_x = (width - self.image.width) / 2.0
        self.offset_y = (height - self.image.height) / 2.0
        self.fit_active = False
        self._schedule_render()
        self._report_zoom()

    def _on_configure(self, _event=None) -> None:
        if self.fit_active and self.image is not None:
            self.fit()
        else:
            self._schedule_render()

    def _on_mousewheel(self, event: tk.Event) -> None:
        factor = 1.2 if event.delta > 0 else 1 / 1.2
        self._zoom_at(event.x, event.y, factor)

    def _zoom_at(self, x: float, y: float, factor: float) -> None:
        if self.image is None:
            return
        old_scale = self.scale
        new_scale = min(32.0, max(0.01, old_scale * factor))
        image_x = (x - self.offset_x) / old_scale
        image_y = (y - self.offset_y) / old_scale
        self.scale = new_scale
        self.offset_x = x - image_x * new_scale
        self.offset_y = y - image_y * new_scale
        self.fit_active = False
        self._schedule_render()
        self._report_zoom()

    def _start_pan(self, event: tk.Event) -> None:
        if self.measurement_mode and self.image is not None:
            start = self._canvas_to_image(event.x, event.y)
            if start is not None:
                self._measurement_start = start
                self.measurement_line = (*start, *start)
                self._draw_measurement()
            return
        self._drag_start = (event.x, event.y, self.offset_x, self.offset_y)

    def _pan(self, event: tk.Event) -> None:
        if self._measurement_start is not None:
            end = self._canvas_to_image(event.x, event.y, clamp=True)
            if end is not None:
                self.measurement_line = (*self._measurement_start, *end)
                self._draw_measurement()
            return
        if self._drag_start is None or self.image is None:
            return
        start_x, start_y, offset_x, offset_y = self._drag_start
        self.offset_x = offset_x + event.x - start_x
        self.offset_y = offset_y + event.y - start_y
        self.fit_active = False
        self._schedule_render()

    def _stop_pan(self, _event=None) -> None:
        if self._measurement_start is not None and self.measurement_line is not None:
            x0, y0, x1, y1 = self.measurement_line
            length = hypot(x1 - x0, y1 - y0)
            self._measurement_start = None
            self.set_measurement_mode(False)
            if self._measurement_callback:
                self._measurement_callback(length)
            return
        self._drag_start = None

    def _schedule_render(self) -> None:
        if self._render_job is not None:
            self.after_cancel(self._render_job)
        self._render_job = self.after_idle(self._render)

    def _render(self) -> None:
        self._render_job = None
        self.canvas.delete("image")
        if self.image is None:
            return

        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        left = max(0, int(np.floor(-self.offset_x / self.scale)))
        top = max(0, int(np.floor(-self.offset_y / self.scale)))
        right = min(
            self.image.width,
            int(np.ceil((canvas_width - self.offset_x) / self.scale)),
        )
        bottom = min(
            self.image.height,
            int(np.ceil((canvas_height - self.offset_y) / self.scale)),
        )
        if right <= left or bottom <= top:
            return

        crop = self.image.crop((left, top, right, bottom))
        display_width = max(1, int(round((right - left) * self.scale)))
        display_height = max(1, int(round((bottom - top) * self.scale)))
        if crop.size != (display_width, display_height):
            resample = Image.Resampling.NEAREST if self.scale >= 4 else Image.Resampling.BILINEAR
            crop = crop.resize((display_width, display_height), resample)

        self._photo = ImageTk.PhotoImage(crop)
        screen_x = self.offset_x + left * self.scale
        screen_y = self.offset_y + top * self.scale
        self.canvas.create_image(
            screen_x,
            screen_y,
            image=self._photo,
            anchor="nw",
            tags="image",
        )
        self._draw_measurement()

    def _report_zoom(self) -> None:
        if self._zoom_callback:
            self._zoom_callback(self.scale)

    def _on_motion(self, event: tk.Event) -> None:
        if self.image is None:
            self._report_pixel(None, None)
            return
        image_x = int((event.x - self.offset_x) / self.scale)
        image_y = int((event.y - self.offset_y) / self.scale)
        if 0 <= image_x < self.image.width and 0 <= image_y < self.image.height:
            self._report_pixel(image_x, image_y)
        else:
            self._report_pixel(None, None)

    def _canvas_to_image(
        self, x: float, y: float, clamp: bool = False
    ) -> tuple[float, float] | None:
        if self.image is None:
            return None
        image_x = (x - self.offset_x) / self.scale
        image_y = (y - self.offset_y) / self.scale
        if clamp:
            image_x = min(max(image_x, 0.0), self.image.width - 1.0)
            image_y = min(max(image_y, 0.0), self.image.height - 1.0)
        elif not (0 <= image_x < self.image.width and 0 <= image_y < self.image.height):
            return None
        return image_x, image_y

    def set_measurement_mode(self, enabled: bool) -> None:
        self.measurement_mode = enabled
        self.canvas.configure(cursor="crosshair" if enabled else "fleur")
        if enabled:
            self._drag_start = None
            self._measurement_start = None

    def clear_measurement(self) -> None:
        self.measurement_line = None
        self.canvas.delete("measurement")

    def _draw_measurement(self) -> None:
        self.canvas.delete("measurement")
        if self.measurement_line is None:
            return
        x0, y0, x1, y1 = self.measurement_line
        canvas_points = (
            self.offset_x + x0 * self.scale,
            self.offset_y + y0 * self.scale,
            self.offset_x + x1 * self.scale,
            self.offset_y + y1 * self.scale,
        )
        self.canvas.create_line(
            *canvas_points,
            fill="#ffcc33",
            width=2,
            tags="measurement",
        )
        radius = 3
        for x, y in (canvas_points[:2], canvas_points[2:]):
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill="#ffcc33",
                outline="#202124",
                tags="measurement",
            )

    def _report_pixel(self, x: int | None, y: int | None) -> None:
        if self._pixel_callback:
            self._pixel_callback(x, y)


class HistogramWidget(tk.Canvas):
    """Compact dependency-free histogram for the current scientific image."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(
            master,
            height=105,
            background="#ffffff",
            highlightthickness=1,
            highlightbackground="#b8b8b8",
        )
        self._histogram: np.ndarray | None = None
        self.bind("<Configure>", lambda _event: self._draw())

    def set_data(self, array: np.ndarray, max_samples: int = 500_000) -> None:
        values = np.asarray(array)
        if values.ndim == 3 and values.shape[-1] in (3, 4):
            values = values[..., :3]
        values = values.reshape(-1)
        if values.size > max_samples:
            step = max(1, values.size // max_samples)
            values = values[::step][:max_samples]
        values = values[np.isfinite(values)]
        if values.size:
            low, high = np.percentile(values, [0.1, 99.9])
            if high <= low:
                high = low + 1.0
            histogram, _ = np.histogram(values, bins=96, range=(float(low), float(high)))
            self._histogram = np.log1p(histogram.astype(np.float64))
        else:
            self._histogram = None
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        if self._histogram is None or not self._histogram.size:
            return
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        maximum = float(self._histogram.max()) or 1.0
        bar_width = width / self._histogram.size
        for index, value in enumerate(self._histogram):
            x0 = index * bar_width
            x1 = (index + 1) * bar_width + 1
            y0 = height - (float(value) / maximum) * (height - 5)
            self.create_rectangle(x0, y0, x1, height, fill="#657b9a", outline="")


class TiffViewer(tk.Tk):
    def __init__(self, initial_path: str | os.PathLike[str] | None = None) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x760")
        self.minsize(850, 680)

        self.tiff: tifffile.TiffFile | None = None
        self.path: Path | None = None
        self.raw_array: np.ndarray | None = None
        self.display_image: Image.Image | None = None
        self.statistics: ImageStatistics | None = None
        self.page_count = 0
        self._contrast_job: str | None = None
        self.calibration_store = CalibrationStore()
        self.calibrations = self.calibration_store.load()
        self.active_calibration: Calibration | None = None
        self._line_action: str | None = None

        self.low_percentile = tk.DoubleVar(value=1.0)
        self.high_percentile = tk.DoubleVar(value=99.0)
        self.invert = tk.BooleanVar(value=False)
        self.page_number = tk.IntVar(value=1)
        self.info_text = tk.StringVar(value="Apri un'immagine TIFF per iniziare")
        self.zoom_text = tk.StringVar(value="")
        self.limits_text = tk.StringVar(value="")
        self.pixel_text = tk.StringVar(value="")
        self.calibration_name = tk.StringVar(value="Nessuna")
        self.measurement_text = tk.StringVar(value="Nessuna misura")

        self._configure_style()
        self._build_ui()
        self._build_menu()
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.bind("<Control-o>", lambda _event: self.open_dialog())
        self.bind("<Control-s>", lambda _event: self.export_png())
        self.bind("<Key-f>", lambda _event: self.viewer.fit())
        self.bind("<Key-1>", lambda _event: self.viewer.actual_size())

        if initial_path:
            self.after_idle(lambda: self.open_file(initial_path))

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Toolbar.TFrame", background="#f4f5f6")
        style.configure("Title.TLabel", font=("TkDefaultFont", 10, "bold"))

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Apri…", accelerator="Ctrl+O", command=self.open_dialog)
        file_menu.add_command(
            label="Esporta vista in PNG…",
            accelerator="Ctrl+S",
            command=self.export_png,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Esci", command=self._close)
        menu.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Adatta alla finestra", accelerator="F", command=self.viewer.fit)
        view_menu.add_command(label="Dimensione reale", accelerator="1", command=self.viewer.actual_size)
        view_menu.add_command(label="Contrasto automatico", command=self.auto_contrast)
        menu.add_cascade(label="Visualizza", menu=view_menu)
        self.configure(menu=menu)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(8, 7))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Apri TIFF", command=self.open_dialog).pack(side="left")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="Adatta", command=lambda: self.viewer.fit()).pack(side="left")
        ttk.Button(toolbar, text="100%", command=lambda: self.viewer.actual_size()).pack(
            side="left", padx=(5, 0)
        )
        ttk.Button(toolbar, text="Auto contrasto", command=self.auto_contrast).pack(
            side="left", padx=(8, 0)
        )
        ttk.Checkbutton(
            toolbar,
            text="Inverti",
            variable=self.invert,
            command=self._schedule_contrast_update,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Esporta PNG", command=self.export_png).pack(side="right")

        content = ttk.Frame(self)
        content.pack(fill="both", expand=True)
        side = ttk.Frame(content, padding=12, width=230)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        ttk.Label(side, text="Contrasto", style="Title.TLabel").pack(anchor="w")
        ttk.Label(side, text="Istogramma (scala log)").pack(anchor="w", pady=(12, 3))
        self.histogram = HistogramWidget(side)
        self.histogram.pack(fill="x")
        ttk.Label(side, text="Nero · percentile basso").pack(anchor="w", pady=(12, 0))
        low_scale = ttk.Scale(
            side,
            from_=0.0,
            to=20.0,
            variable=self.low_percentile,
            command=lambda _value: self._on_contrast_control(),
        )
        low_scale.pack(fill="x")
        self.low_label = ttk.Label(side, text="1,0%")
        self.low_label.pack(anchor="e")

        ttk.Label(side, text="Bianco · percentile alto").pack(anchor="w", pady=(10, 0))
        high_scale = ttk.Scale(
            side,
            from_=80.0,
            to=100.0,
            variable=self.high_percentile,
            command=lambda _value: self._on_contrast_control(),
        )
        high_scale.pack(fill="x")
        self.high_label = ttk.Label(side, text="99,0%")
        self.high_label.pack(anchor="e")

        ttk.Label(side, textvariable=self.limits_text, wraplength=205).pack(
            anchor="w", pady=(14, 0)
        )
        ttk.Button(side, text="Informazioni scientifiche…", command=self.show_information).pack(
            fill="x", pady=(12, 0)
        )

        self.page_panel = ttk.Frame(side)
        self.page_panel.pack(fill="x", pady=(22, 0))
        ttk.Label(self.page_panel, text="Pagina", style="Title.TLabel").pack(anchor="w")
        page_line = ttk.Frame(self.page_panel)
        page_line.pack(fill="x", pady=(6, 0))
        ttk.Button(page_line, text="‹", width=3, command=lambda: self.change_page(-1)).pack(
            side="left"
        )
        self.page_spin = ttk.Spinbox(
            page_line,
            from_=1,
            to=1,
            width=6,
            textvariable=self.page_number,
            command=self._load_selected_page,
        )
        self.page_spin.pack(side="left", padx=5)
        self.page_total_label = ttk.Label(page_line, text="di 1")
        self.page_total_label.pack(side="left")
        ttk.Button(page_line, text="›", width=3, command=lambda: self.change_page(1)).pack(
            side="right"
        )
        self.page_spin.bind("<Return>", lambda _event: self._load_selected_page())

        ttk.Separator(side).pack(fill="x", pady=(20, 12))
        ttk.Label(side, text="Scala e misure", style="Title.TLabel").pack(anchor="w")
        self.calibration_combo = ttk.Combobox(
            side,
            state="readonly",
            textvariable=self.calibration_name,
            values=["Nessuna", *sorted(self.calibrations)],
        )
        self.calibration_combo.pack(fill="x", pady=(7, 0))
        self.calibration_combo.bind("<<ComboboxSelected>>", self._select_calibration)
        calibration_buttons = ttk.Frame(side)
        calibration_buttons.pack(fill="x", pady=(7, 0))
        ttk.Button(
            calibration_buttons,
            text="Calibra…",
            command=self.begin_calibration,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            calibration_buttons,
            text="Misura",
            command=self.begin_measurement,
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Label(side, textvariable=self.measurement_text, wraplength=205).pack(
            anchor="w", pady=(7, 0)
        )

        ttk.Separator(side).pack(fill="x", pady=(22, 12))
        ttk.Label(
            side,
            text="Rotella: zoom\nTrascina: sposta\nF: adatta · 1: 100%",
            foreground="#555555",
            justify="left",
        ).pack(anchor="w")

        self.viewer = ViewerCanvas(
            content,
            zoom_callback=self._set_zoom,
            pixel_callback=self._set_pixel_readout,
            measurement_callback=self._measurement_complete,
        )
        self.viewer.pack(side="left", fill="both", expand=True)

        status = ttk.Frame(self, padding=(9, 5))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.info_text).pack(side="left")
        ttk.Label(status, textvariable=self.pixel_text).pack(side="left", padx=(18, 0))
        ttk.Label(status, textvariable=self.zoom_text).pack(side="right")

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(title="Apri immagine TIFF", filetypes=TIFF_TYPES)
        if path:
            self.open_file(path)

    def open_file(self, path: str | os.PathLike[str]) -> None:
        candidate = Path(path).expanduser()
        try:
            new_tiff = tifffile.TiffFile(candidate)
            if not new_tiff.pages:
                raise ValueError("Il file non contiene immagini")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Impossibile aprire il TIFF:\n{exc}")
            return

        if self.tiff is not None:
            self.tiff.close()
        self.tiff = new_tiff
        self.path = candidate
        self.page_count = len(new_tiff.pages)
        self.page_number.set(1)
        self.page_spin.configure(to=self.page_count)
        self.page_total_label.configure(text=f"di {self.page_count}")
        self.page_panel.pack_configure()
        self.title(f"{candidate.name} — {APP_NAME}")
        self._load_page(0)

    def _load_selected_page(self) -> None:
        try:
            index = int(self.page_number.get()) - 1
        except (ValueError, tk.TclError):
            return
        index = max(0, min(self.page_count - 1, index))
        self.page_number.set(index + 1)
        self._load_page(index)

    def change_page(self, delta: int) -> None:
        if self.tiff is None:
            return
        index = max(0, min(self.page_count - 1, self.page_number.get() - 1 + delta))
        if index != self.page_number.get() - 1:
            self.page_number.set(index + 1)
            self._load_page(index)

    def _load_page(self, index: int) -> None:
        if self.tiff is None:
            return
        try:
            self.configure(cursor="watch")
            self.update_idletasks()
            array = self.tiff.pages[index].asarray()
            self.raw_array = np.asarray(array)
            self.statistics = image_statistics(self.raw_array)
            self.viewer.clear_measurement()
            self.histogram.set_data(self.raw_array)
            self.auto_contrast()
            height, width = self.raw_array.shape[:2]
            stats = self.statistics
            finite_note = ""
            if stats.finite_count != stats.total_count:
                finite_note = f" · {stats.total_count - stats.finite_count} non finiti"
            self.info_text.set(
                f"{width} × {height} px · {self.raw_array.dtype} · "
                f"min {stats.minimum:.6g} · max {stats.maximum:.6g}{finite_note}"
            )
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Impossibile leggere la pagina {index + 1}:\n{exc}")
        finally:
            self.configure(cursor="")

    def auto_contrast(self) -> None:
        self.low_percentile.set(1.0)
        self.high_percentile.set(99.0)
        self._update_contrast()

    def _on_contrast_control(self) -> None:
        low = self.low_percentile.get()
        high = self.high_percentile.get()
        self.low_label.configure(text=f"{low:.1f}%".replace(".", ","))
        self.high_label.configure(text=f"{high:.1f}%".replace(".", ","))
        self._schedule_contrast_update()

    def _schedule_contrast_update(self) -> None:
        if self._contrast_job is not None:
            self.after_cancel(self._contrast_job)
        self._contrast_job = self.after(120, self._update_contrast)

    def _update_contrast(self) -> None:
        self._contrast_job = None
        if self.raw_array is None:
            return
        low_p = self.low_percentile.get()
        high_p = self.high_percentile.get()
        if low_p >= high_p:
            return
        try:
            black, white = contrast_limits(self.raw_array, low_p, high_p)
            self.display_image = to_display_image(
                self.raw_array,
                black,
                white,
                invert=self.invert.get(),
            )
            preserve_view = self.viewer.image is not None and not self.viewer.fit_active
            old_scale = self.viewer.scale
            old_offsets = (self.viewer.offset_x, self.viewer.offset_y)
            self.viewer.set_image(self.display_image, fit=not preserve_view)
            if preserve_view:
                self.viewer.scale = old_scale
                self.viewer.offset_x, self.viewer.offset_y = old_offsets
                self.viewer.fit_active = False
                self.viewer._schedule_render()
            self.limits_text.set(f"Visualizzazione: {black:.6g} → {white:.6g}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def export_png(self) -> None:
        if self.display_image is None or self.path is None:
            messagebox.showinfo(APP_NAME, "Apri prima un'immagine TIFF.")
            return
        suggested = self.path.with_suffix(".png").name
        path = filedialog.asksaveasfilename(
            title="Esporta immagine visualizzata",
            defaultextension=".png",
            initialfile=suggested,
            filetypes=[("Immagine PNG", "*.png")],
        )
        if not path:
            return
        try:
            self.display_image.save(path, format="PNG")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Impossibile esportare il PNG:\n{exc}")

    def _set_zoom(self, scale: float) -> None:
        self.zoom_text.set(f"Zoom {scale * 100:.0f}%")

    def _set_pixel_readout(self, x: int | None, y: int | None) -> None:
        if x is None or y is None or self.raw_array is None:
            self.pixel_text.set("")
            return
        try:
            value = self.raw_array[y, x]
            if np.ndim(value) == 0:
                text_value = f"{float(value):.7g}"
            else:
                components = np.asarray(value).reshape(-1)
                text_value = "[" + ", ".join(f"{float(item):.7g}" for item in components) + "]"
            self.pixel_text.set(f"x {x} · y {y} · intensità {text_value}")
        except (IndexError, TypeError, ValueError):
            self.pixel_text.set("")

    def show_information(self) -> None:
        if self.tiff is None or self.raw_array is None or self.path is None:
            messagebox.showinfo(APP_NAME, "Apri prima un'immagine TIFF.")
            return
        index = self.page_number.get() - 1
        page = self.tiff.pages[index]
        data = np.asarray(self.raw_array)
        flat = data.reshape(-1)
        if flat.size > 1_000_000:
            flat = flat[:: max(1, flat.size // 1_000_000)][:1_000_000]
        finite = flat[np.isfinite(flat)]
        mean = float(np.mean(finite)) if finite.size else float("nan")
        deviation = float(np.std(finite)) if finite.size else float("nan")

        lines = [
            f"File: {self.path}",
            f"Dimensione file: {self.path.stat().st_size / (1024 * 1024):.2f} MiB",
            f"Pagina: {index + 1} di {self.page_count}",
            f"Forma dati: {data.shape}",
            f"Tipo dati: {data.dtype}",
            f"Minimo: {self.statistics.minimum:.9g}",
            f"Massimo: {self.statistics.maximum:.9g}",
            f"Media (campionata): {mean:.9g}",
            f"Deviazione standard (campionata): {deviation:.9g}",
            "",
            "Metadati TIFF:",
        ]
        for tag in page.tags.values():
            value = str(tag.value)
            if len(value) > 160:
                value = value[:157] + "…"
            lines.append(f"{tag.name}: {value}")

        window = tk.Toplevel(self)
        window.title(f"Informazioni — {self.path.name}")
        window.geometry("650x520")
        window.transient(self)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="word", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        ttk.Button(window, text="Chiudi", command=window.destroy).pack(pady=(0, 10))

    def _select_calibration(self, _event=None) -> None:
        name = self.calibration_name.get()
        self.active_calibration = self.calibrations.get(name)
        if self.active_calibration:
            value = self.active_calibration.micrometers_per_pixel
            self.measurement_text.set(f"Scala: {value:.7g} µm/pixel")
        else:
            self.measurement_text.set("Nessuna calibrazione attiva")

    def begin_calibration(self) -> None:
        if self.raw_array is None:
            messagebox.showinfo(APP_NAME, "Apri prima l'immagine del vetrino graduato.")
            return
        messagebox.showinfo(
            "Calibrazione manuale",
            "Trascina una linea tra due tacche di distanza nota. "
            "Al rilascio potrai inserire la distanza in micrometri.",
        )
        self._line_action = "calibrate"
        self.viewer.set_measurement_mode(True)
        self.measurement_text.set("Traccia la distanza nota sul vetrino…")

    def begin_measurement(self) -> None:
        if self.raw_array is None:
            messagebox.showinfo(APP_NAME, "Apri prima un'immagine TIFF.")
            return
        self._line_action = "measure"
        self.viewer.set_measurement_mode(True)
        self.measurement_text.set("Traccia il segmento da misurare…")

    def _measurement_complete(self, pixels: float) -> None:
        action = self._line_action
        self._line_action = None
        if pixels < 1.0:
            self.measurement_text.set("Segmento troppo corto")
            return
        if action == "calibrate":
            known_distance = simpledialog.askfloat(
                "Distanza nota",
                f"Il segmento misura {pixels:.2f} pixel.\n"
                "Inserisci la distanza reale in µm:",
                parent=self,
                minvalue=0.000001,
            )
            if known_distance is None:
                self.measurement_text.set("Calibrazione annullata")
                return
            name = simpledialog.askstring(
                "Nome del profilo",
                "Nome del profilo (es. 10×, 40×):",
                parent=self,
            )
            if not name or not name.strip():
                self.measurement_text.set("Calibrazione annullata")
                return
            calibration = Calibration(name.strip(), known_distance / pixels)
            self.calibrations[calibration.name] = calibration
            try:
                self.calibration_store.save(self.calibrations)
            except OSError as exc:
                messagebox.showwarning(APP_NAME, f"Profilo non salvato su disco:\n{exc}")
            self.calibration_combo.configure(values=["Nessuna", *sorted(self.calibrations)])
            self.calibration_name.set(calibration.name)
            self.active_calibration = calibration
            self.measurement_text.set(
                f"{calibration.name}: {calibration.micrometers_per_pixel:.7g} µm/pixel"
            )
            return

        if self.active_calibration:
            micrometers = self.active_calibration.convert(pixels)
            self.measurement_text.set(f"Misura: {pixels:.2f} px · {micrometers:.6g} µm")
        else:
            self.measurement_text.set(f"Misura: {pixels:.2f} px · scala non calibrata")

    def _close(self) -> None:
        if self.tiff is not None:
            self.tiff.close()
        self.destroy()


def main() -> None:
    initial_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = TiffViewer(initial_path)
    app.mainloop()


if __name__ == "__main__":
    main()

