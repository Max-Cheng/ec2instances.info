from __future__ import annotations

import unittest

from scripts.china_cloud.common import (
    classify_category,
    format_packet_rate,
    merge_instances,
    normalize_architecture,
)


class CommonTests(unittest.TestCase):
    def test_formats_packet_rates_with_readable_units(self) -> None:
        self.assertEqual(format_packet_rate(300_000), "300 Kpps")
        self.assertEqual(format_packet_rate(1_200_000), "1.2 Mpps")
        self.assertEqual(format_packet_rate(0), "")

    def test_merges_regional_availability_by_instance_type(self) -> None:
        records = [
            {
                "instanceType": "ecs.g8i.large",
                "family": "g8i",
                "vCPU": 2,
                "memoryGiB": 8,
                "architecture": "x86",
                "sourceUrl": "https://example.invalid/specs",
                "regions": ["cn-a"],
                "zones": ["cn-a-1"],
            },
            {
                "instanceType": "ecs.g8i.large",
                "family": "g8i",
                "vCPU": 2,
                "memoryGiB": 8,
                "sourceUrl": "https://example.invalid/specs",
                "regions": ["cn-b"],
                "zones": ["cn-b-1"],
            },
        ]

        merged = merge_instances(records)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["regions"], ["cn-a", "cn-b"])
        self.assertEqual(merged[0]["availableRegionCount"], 2)
        self.assertEqual(merged[0]["availableZoneCount"], 2)

    def test_classifies_common_shapes(self) -> None:
        self.assertEqual(
            classify_category("c8i", "ecs.c8i.large", 2, 4),
            "Compute optimized",
        )
        self.assertEqual(
            classify_category("m8i", "ecs.m8i.large", 2, 16),
            "Memory optimized",
        )
        self.assertEqual(
            classify_category("gn7", "ecs.gn7.large", 4, 16, gpu_count=1),
            "Accelerated computing",
        )

    def test_normalizes_architecture(self) -> None:
        self.assertEqual(normalize_architecture("ARMv8"), "arm64")
        self.assertEqual(normalize_architecture("Intel Xeon"), "x86_64")
        self.assertEqual(normalize_architecture(None), "unknown")


if __name__ == "__main__":
    unittest.main()
