"""Image conversion utilities kept separate from the user interface."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ImageStatistics:
    minimum: float
    maximum: float
    finite_count: int
    total_count: int


def image_statistics(array: np.ndarray) -> ImageStatistics:
    """Return finite-value statistics without failing on NaN-only images."""
    values = np.asarray(array)
    if values.ndim == 3 and values.shape[-1] in (3, 4):
        values = values[..., :3]
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return ImageStatistics(0.0, 0.0, 0, int(values.size))
    return ImageStatistics(
        float(finite.min()),
        float(finite.max()),
        int(finite.size),
        int(values.size),
    )


def contrast_limits(
    array: np.ndarray,
    low_percentile: float = 1.0,
    high_percentile: float = 99.0,
    max_samples: int = 1_000_000,
) -> tuple[float, float]:
    """Calculate robust display limits from a bounded, evenly-spaced sample."""
    if not 0.0 <= low_percentile < high_percentile <= 100.0:
        raise ValueError("Percentili di contrasto non validi")

    values = np.asarray(array)
    if values.ndim == 3 and values.shape[-1] in (3, 4):
        values = values[..., :3]
    values = values.reshape(-1)
    if values.size > max_samples:
        step = max(1, values.size // max_samples)
        values = values[::step][:max_samples]
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0.0, 1.0

    low, high = np.percentile(values, [low_percentile, high_percentile])
    low = float(low)
    high = float(high)
    if high <= low:
        high = low + 1.0
    return low, high


def _scale_channel(array: np.ndarray, black: float, white: float) -> np.ndarray:
    data = np.asarray(array, dtype=np.float32)
    data = np.nan_to_num(data, nan=black, posinf=white, neginf=black)
    scaled = (data - black) * (255.0 / (white - black))
    return np.clip(scaled, 0.0, 255.0).astype(np.uint8)


def to_display_image(
    array: np.ndarray,
    black: float,
    white: float,
    invert: bool = False,
) -> Image.Image:
    """Convert common TIFF array layouts to an 8-bit Pillow display image."""
    if white <= black:
        raise ValueError("Il punto di bianco deve superare il punto di nero")

    data = np.asarray(array)
    # Remove only container axes commonly produced by TIFF series.  A blanket
    # squeeze would turn a valid 1xN grayscale image or 1x1 RGB image into 1D.
    while data.ndim > 3 and data.shape[0] == 1:
        data = data[0]
    if data.ndim == 3 and data.shape[-1] not in (3, 4) and data.shape[0] == 1:
        data = data[0]
    if data.ndim == 2:
        converted = _scale_channel(data, black, white)
        if invert:
            converted = 255 - converted
        return Image.fromarray(converted, mode="L")

    if data.ndim == 3 and data.shape[-1] in (3, 4):
        rgb = _scale_channel(data[..., :3], black, white)
        if invert:
            rgb = 255 - rgb
        if data.shape[-1] == 4:
            alpha = data[..., 3]
            if alpha.dtype == np.uint8:
                alpha8 = alpha
            else:
                alpha_stats = image_statistics(alpha)
                alpha_max = alpha_stats.maximum if alpha_stats.maximum > 0 else 1.0
                alpha8 = _scale_channel(alpha, 0.0, alpha_max)
            rgba = np.dstack((rgb, alpha8))
            return Image.fromarray(rgba, mode="RGBA")
        return Image.fromarray(rgb, mode="RGB")

    raise ValueError(
        f"Formato pixel non supportato: forma {data.shape}. "
        "Sono accettate immagini 2D, RGB e RGBA."
    )

