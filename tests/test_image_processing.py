import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from tiff_viewer.image_processing import contrast_limits, image_statistics, to_display_image
from tiff_viewer.calibration import Calibration, CalibrationStore


class ImageProcessingTests(unittest.TestCase):
    # Include both sides of the old stride transitions and a typical large TIFF.
    LARGE_SHAPES = (
        (1, 1_000_001),
        (1001, 1000),
        (1500, 1000),
        (1999, 1000),
        (2001, 1000),
        (2500, 1000),
        (2448, 2048),
    )

    def test_large_gradients_match_full_image_percentiles(self):
        for shape in self.LARGE_SHAPES:
            for dtype in (np.float32, np.float64):
                with self.subTest(shape=shape, dtype=dtype):
                    data = np.arange(np.prod(shape), dtype=dtype).reshape(shape)
                    expected = np.percentile(data, [1.0, 99.0])
                    # Integer sampling positions may shift a quantile by at
                    # most one intensity unit on this unit-step gradient.
                    np.testing.assert_allclose(
                        contrast_limits(data), expected, rtol=0.0, atol=1.0
                    )

    def test_large_sample_is_bounded_and_reaches_both_image_ends(self):
        for shape in self.LARGE_SHAPES:
            with self.subTest(shape=shape):
                data = np.arange(np.prod(shape), dtype=np.float64).reshape(shape)
                with patch(
                    "tiff_viewer.image_processing.np.percentile",
                    wraps=np.percentile,
                ) as percentile:
                    limits = contrast_limits(data, 0.0, 100.0)
                sample = percentile.call_args.args[0]
                self.assertLessEqual(sample.size, 1_000_000)
                self.assertEqual(limits, (0.0, float(data.size - 1)))
                gaps = np.diff(sample)
                self.assertTrue(np.all(gaps > 0))
                self.assertLessEqual(float(gaps.max() - gaps.min()), 1.0)

    def test_spatial_intensity_bands_match_full_image_percentiles(self):
        for shape in self.LARGE_SHAPES[1:]:
            with self.subTest(shape=shape):
                data = np.full(shape, 10.0, dtype=np.float32)
                # A bright lower third was entirely missed in the 1500x1000
                # case; reversing the image tests the opposite intensity order.
                data[2 * shape[0] // 3:] = 1000.0
                for image in (data, data[::-1]):
                    with self.subTest(reversed=image.strides[0] < 0):
                        expected = np.percentile(image, [1.0, 99.0])
                        np.testing.assert_array_equal(contrast_limits(image), expected)

    def test_sampled_percentiles_ignore_nan_and_both_infinities(self):
        for shape in self.LARGE_SHAPES[1:]:
            for pattern in ("scattered", "blocks"):
                with self.subTest(shape=shape, pattern=pattern):
                    data = np.linspace(-50.0, 150.0, np.prod(shape)).reshape(shape)
                    flat = data.reshape(-1)
                    if pattern == "scattered":
                        flat[::11] = np.nan
                        flat[3::17] = np.inf
                        flat[5::23] = -np.inf
                    else:
                        width = flat.size // 10
                        flat[:width] = np.nan
                        flat[4 * width:5 * width] = np.inf
                        flat[-width:] = -np.inf
                    expected = np.percentile(data[np.isfinite(data)], [1.0, 99.0])
                    actual = contrast_limits(data)
                    self.assertTrue(np.all(np.isfinite(actual)))
                    # 0.01 intensity units is 0.005% of this gradient's range;
                    # allow finite-sample rank changes, not a cropped region.
                    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.01)

    def test_small_and_exact_budget_images_use_all_finite_values(self):
        for shape in ((8, 9), (1000, 1000)):
            with self.subTest(shape=shape):
                data = np.linspace(-2.0, 3.0, np.prod(shape)).reshape(shape)
                data.flat[::19] = np.nan
                expected = np.percentile(data[np.isfinite(data)], [1.0, 99.0])
                np.testing.assert_array_equal(contrast_limits(data), expected)

    def test_custom_sample_budget(self):
        data = np.arange(101, dtype=np.float64).reshape(1, -1)
        for budget in (1, 2, 7, 100, 101, 102):
            with self.subTest(budget=budget):
                with patch(
                    "tiff_viewer.image_processing.np.percentile",
                    wraps=np.percentile,
                ) as percentile:
                    limits = contrast_limits(data, 0.0, 100.0, max_samples=budget)
                self.assertLessEqual(percentile.call_args.args[0].size, budget)
                if budget == 1:
                    self.assertEqual(limits, (0.0, 1.0))
                else:
                    self.assertEqual(limits, (0.0, 100.0))

    def test_non_positive_sample_budget_is_rejected(self):
        for budget in (0, -1):
            with self.subTest(budget=budget):
                with self.assertRaises(ValueError):
                    contrast_limits(np.arange(10), max_samples=budget)

    def test_empty_and_all_non_finite_images_have_default_limits(self):
        self.assertEqual(contrast_limits(np.empty((0, 0))), (0.0, 1.0))
        data = np.resize([np.nan, np.inf, -np.inf], (1001, 1000))
        self.assertEqual(contrast_limits(data), (0.0, 1.0))

    def test_large_constant_image_has_valid_contrast_range(self):
        data = np.full((1500, 1000), 7.0, dtype=np.float32)
        data.flat[::13] = np.nan
        self.assertEqual(contrast_limits(data), (7.0, 8.0))

    def test_contrast_preserves_raw_data_and_full_image_statistics(self):
        for dtype in (np.uint16, np.float32, np.float64):
            with self.subTest(dtype=dtype):
                data = np.linspace(1.0, 100.0, 1_500_000).astype(dtype).reshape(1500, 1000)
                data[0, 0] = 0
                data[-1, -1] = 500
                if np.issubdtype(dtype, np.floating):
                    data[0, 1:4] = [np.nan, np.inf, -np.inf]
                original = data.copy()
                before = image_statistics(data)
                self.assertEqual(before.minimum, 0.0)
                self.assertEqual(before.maximum, 500.0)
                self.assertEqual(before.total_count, data.size)
                self.assertEqual(before.finite_count, int(np.isfinite(data).sum()))
                data.flags.writeable = False
                first_limits = contrast_limits(data)
                self.assertEqual(first_limits, contrast_limits(data))
                np.testing.assert_array_equal(data, original)
                self.assertEqual(data.dtype, original.dtype)
                self.assertEqual(image_statistics(data), before)

    def test_color_contrast_ignores_alpha_and_supports_non_contiguous_input(self):
        rgb = np.arange(90, dtype=np.float32).reshape(5, 6, 3)
        rgba = np.dstack((rgb, np.full((5, 6), 1e20, dtype=np.float32)))
        for image in (rgba, rgba[::-1, ::-1]):
            with self.subTest(reversed=image.strides[0] < 0):
                expected = contrast_limits(image[..., :3].copy(), max_samples=17)
                self.assertEqual(contrast_limits(image, max_samples=17), expected)

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

