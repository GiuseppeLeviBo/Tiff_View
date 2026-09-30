import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from tiff_viewer.image_processing import contrast_limits, image_statistics, to_display_image
from tiff_viewer.calibration import Calibration, CalibrationStore


class ImageProcessingTests(unittest.TestCase):
    def test_statistics_ignore_non_finite_values(self):
        data = np.array([[1.0, np.nan], [np.inf, 3.0]], dtype=np.float32)
        stats = image_statistics(data)
        self.assertEqual(stats.minimum, 1.0)
        self.assertEqual(stats.maximum, 3.0)
        self.assertEqual(stats.finite_count, 2)
        self.assertEqual(stats.total_count, 4)

    def test_constant_image_has_valid_contrast_range(self):
        low, high = contrast_limits(np.full((20, 20), 7.0, dtype=np.float32))
        self.assertEqual(low, 7.0)
        self.assertEqual(high, 8.0)

    def test_float_grayscale_is_scaled_and_clipped(self):
        data = np.array([[-1.0, 0.0, 0.5, 1.0, 2.0]], dtype=np.float32)
        image = to_display_image(data, 0.0, 1.0)
        self.assertEqual(image.mode, "L")
        self.assertEqual(list(np.asarray(image)[0]), [0, 0, 127, 255, 255])

    def test_inversion(self):
        data = np.array([[0.0, 1.0]], dtype=np.float32)
        image = to_display_image(data, 0.0, 1.0, invert=True)
        self.assertEqual(list(np.asarray(image)[0]), [255, 0])

    def test_rgb_is_supported(self):
        data = np.array([[[0.0, 0.5, 1.0]]], dtype=np.float32)
        image = to_display_image(data, 0.0, 1.0)
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(tuple(np.asarray(image)[0, 0]), (0, 127, 255))

    def test_invalid_percentile_order_is_rejected(self):
        with self.assertRaises(ValueError):
            contrast_limits(np.arange(10), 99.0, 1.0)

    def test_calibration_conversion_and_persistence(self):
        calibration = Calibration("40×", 0.125)
        self.assertEqual(calibration.convert(80), 10.0)
        with TemporaryDirectory() as directory:
            store = CalibrationStore(Path(directory) / "calibrations.json")
            store.save({calibration.name: calibration})
            loaded = store.load()
        self.assertEqual(loaded["40×"], calibration)


if __name__ == "__main__":
    unittest.main()

