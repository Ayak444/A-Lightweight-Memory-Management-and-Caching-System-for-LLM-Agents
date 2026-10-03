from __future__ import annotations

import unittest
from pathlib import Path

from memlite.evaluation.datasets import REQUIRED_CATEGORIES, load_dataset


class DatasetTestCase(unittest.TestCase):
    def test_mvp_dataset_is_valid_and_covers_required_categories(self) -> None:
        dataset_path = Path("experiments/datasets/mvp.json")

        dataset = load_dataset(dataset_path)

        self.assertEqual(dataset.version, "1.0.0")
        self.assertEqual(len(dataset.sequences), 10)
        self.assertTrue(REQUIRED_CATEGORIES.issubset(dataset.categories))


if __name__ == "__main__":
    unittest.main()
