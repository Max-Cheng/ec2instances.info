from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from scripts import update_china_clouds


OLD_GENERATED_AT = "2026-01-01T00:00:00Z"


def instance(instance_type: str) -> dict[str, object]:
    return {
        "instanceType": instance_type,
        "family": "test",
        "familyName": "Test",
        "category": "General purpose",
        "vCPU": 2,
        "memoryGiB": 4,
        "architecture": "x86_64",
        "processor": "Test CPU",
        "networkPerformance": "Test network",
        "localStorage": "Cloud disks",
        "sourceUrl": "https://example.com/catalog",
        "regions": ["region-1"],
        "zones": ["region-1a"],
        "availableRegionCount": 1,
        "availableZoneCount": 1,
    }


def provider(slug: str, version: str = "old") -> dict[str, object]:
    item = instance(f"{slug}.{version}")
    if slug in update_china_clouds.PRICE_PROVIDER_SLUGS:
        item["onDemandPrices"] = {
            "region-1": {"amount": "0.25", "currency": "CNY", "unit": "hour"}
        }
    return {
        "slug": slug,
        "regionCount": 1,
        "zoneCount": 1,
        "instances": [item],
    }


def catalog(version: str = "old") -> dict[str, object]:
    providers = {
        slug: provider(slug, version)
        for slug in update_china_clouds.PROVIDER_SLUGS
    }
    return update_china_clouds.build_catalog(providers, OLD_GENERATED_AT)


class UpdateChinaCloudsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.minimum_counts = mock.patch.dict(
            update_china_clouds.MINIMUM_INSTANCE_COUNTS,
            {slug: 1 for slug in update_china_clouds.PROVIDER_SLUGS},
        )
        self.minimum_counts.start()
        self.prepare_provider = mock.patch.object(
            update_china_clouds, "prepare_provider"
        )
        self.prepare_provider_mock = self.prepare_provider.start()

    def tearDown(self) -> None:
        self.prepare_provider.stop()
        self.minimum_counts.stop()

    def args(self, root: Path, previous: Path | None) -> argparse.Namespace:
        return argparse.Namespace(
            providers=None,
            output=root / "generated.json",
            public_output=root / "public.json",
            previous=previous,
            checkpoint=root / "checkpoint.json",
            failure_marker=root / "provider-failed",
            completion_marker=root / "provider-completed",
            validate_only=None,
        )

    def write_catalog(self, path: Path, value: dict[str, object]) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_validate_catalog_requires_consistent_full_totals(self) -> None:
        value = catalog()
        update_china_clouds.validate_catalog(value)

        value["totals"]["uniqueInstanceTypes"] = 99
        with self.assertRaisesRegex(ValueError, "instance total mismatch"):
            update_china_clouds.validate_catalog(value)

    def test_validate_provider_rejects_missing_or_misattributed_prices(self) -> None:
        value = provider("alibaba")
        value["instances"][0].pop("onDemandPrices")
        with self.assertRaisesRegex(ValueError, "no public Linux on-demand prices"):
            update_china_clouds.validate_provider(
                "alibaba", value, require_prices=True
            )

        value = provider("alibaba")
        value["instances"][0]["onDemandPrices"] = {
            "other-region": {
                "amount": "0.25",
                "currency": "CNY",
                "unit": "hour",
            }
        }
        with self.assertRaisesRegex(ValueError, "price regions are not in availability"):
            update_china_clouds.validate_provider("alibaba", value)

    def test_schema_one_legacy_catalog_can_seed_the_price_rollout(self) -> None:
        value = catalog()
        value["schemaVersion"] = 1
        for slug in update_china_clouds.PRICE_PROVIDER_SLUGS:
            value["providers"][slug]["instances"][0].pop("onDemandPrices")
        update_china_clouds.validate_catalog(value)

        value["schemaVersion"] = 2
        with self.assertRaisesRegex(ValueError, "no public Linux on-demand prices"):
            update_china_clouds.validate_catalog(value)

    def test_schema_three_validates_subscription_and_spot_prices(self) -> None:
        value = catalog()
        item = value["providers"]["alibaba"]["instances"][0]
        item["subscriptionPrices"] = {
            "region-1": {
                "amount": "0.2",
                "totalAmount": "1752",
                "currency": "CNY",
                "unit": "hour",
                "term": "1-year",
                "payment": "all-upfront",
            }
        }
        item["spotPrices"] = {
            "region-1": {
                "amount": "0.08",
                "currency": "CNY",
                "unit": "hour",
                "zone": "region-1a",
            }
        }
        value = update_china_clouds.build_catalog(
            value["providers"], OLD_GENERATED_AT
        )

        self.assertEqual(value["schemaVersion"], 3)
        update_china_clouds.validate_catalog(value)

        item = value["providers"]["alibaba"]["instances"][0]
        item["subscriptionPrices"]["region-1"]["term"] = "3-year"
        with self.assertRaisesRegex(ValueError, "invalid one-year subscription"):
            update_china_clouds.validate_catalog(value)

        item["subscriptionPrices"]["region-1"]["term"] = "1-year"
        item["subscriptionPrices"]["region-1"]["amount"] = "999"
        with self.assertRaisesRegex(ValueError, "invalid one-year subscription"):
            update_china_clouds.validate_catalog(value)

        item["subscriptionPrices"]["region-1"]["amount"] = "0.2"
        item["spotPrices"]["region-1"]["zone"] = "unrelated-zone"
        with self.assertRaisesRegex(ValueError, "spot price zones are not in availability"):
            update_china_clouds.validate_catalog(value)

        item["spotPrices"]["region-1"]["zone"] = "region-1a"
        item["spotPrices"]["region-1"]["observedAt"] = "not-a-timestamp"
        with self.assertRaisesRegex(ValueError, "invalid spot price data"):
            update_china_clouds.validate_catalog(value)

    def test_validate_provider_rejects_mixed_price_currencies(self) -> None:
        value = provider("alibaba")
        second = instance("alibaba.second")
        second["onDemandPrices"] = {
            "region-1": {"amount": "0.04", "currency": "USD", "unit": "hour"}
        }
        value["instances"].append(second)

        with self.assertRaisesRegex(ValueError, "mixed price currencies"):
            update_china_clouds.validate_provider("alibaba", value)

    def test_success_writes_valid_checkpoint_and_both_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_path = root / "previous.json"
            self.write_catalog(previous_path, catalog())
            args = self.args(root, previous_path)

            def fetch(slug: str) -> dict[str, object]:
                self.assertTrue(args.checkpoint.exists())
                return provider(slug, "new")

            with mock.patch.object(
                update_china_clouds, "parse_args", return_value=args
            ), mock.patch.object(
                update_china_clouds, "fetch_provider", side_effect=fetch
            ):
                self.assertEqual(update_china_clouds.main(), 0)

            checkpoint = update_china_clouds.load_catalog(args.checkpoint)
            self.assertNotEqual(checkpoint["generatedAt"], OLD_GENERATED_AT)
            for slug in update_china_clouds.PROVIDER_SLUGS:
                self.assertEqual(
                    checkpoint["providers"][slug]["instances"][0]["instanceType"],
                    f"{slug}.new",
                )
            self.assertEqual(args.checkpoint.read_bytes(), args.output.read_bytes())
            self.assertEqual(args.checkpoint.read_bytes(), args.public_output.read_bytes())
            self.assertFalse(args.failure_marker.exists())
            self.assertEqual(
                set(args.completion_marker.read_text(encoding="utf-8").splitlines()),
                set(update_china_clouds.PROVIDER_SLUGS),
            )

    def test_prepares_every_sdk_before_starting_provider_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_path = root / "previous.json"
            self.write_catalog(previous_path, catalog())
            args = self.args(root, previous_path)
            args.providers = ["alibaba", "tencent"]
            prepared: list[str] = []

            self.prepare_provider_mock.side_effect = prepared.append

            def fetch(slug: str) -> dict[str, object]:
                self.assertEqual(prepared, args.providers)
                return provider(slug, "new")

            with mock.patch.object(
                update_china_clouds, "parse_args", return_value=args
            ), mock.patch.object(
                update_china_clouds, "fetch_provider", side_effect=fetch
            ):
                self.assertEqual(update_china_clouds.main(), 0)

            self.assertEqual(prepared, args.providers)

    def test_explicit_provider_failure_marks_error_but_keeps_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_path = root / "previous.json"
            self.write_catalog(previous_path, catalog())
            args = self.args(root, previous_path)

            def fetch(slug: str) -> dict[str, object]:
                if slug == "alibaba":
                    return provider(slug, "new")
                raise RuntimeError(f"{slug} failed")

            with mock.patch.object(
                update_china_clouds, "parse_args", return_value=args
            ), mock.patch.object(
                update_china_clouds, "fetch_provider", side_effect=fetch
            ), redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(update_china_clouds.main(), 1)

            self.assertIn("catalog refresh failed", stderr.getvalue())

            checkpoint = update_china_clouds.load_catalog(args.checkpoint)
            self.assertEqual(checkpoint["generatedAt"], OLD_GENERATED_AT)
            self.assertEqual(
                checkpoint["providers"]["alibaba"]["instances"][0]["instanceType"],
                "alibaba.new",
            )
            self.assertEqual(
                checkpoint["providers"]["tencent"]["instances"][0]["instanceType"],
                "tencent.old",
            )
            self.assertTrue(args.failure_marker.exists())
            self.assertEqual(
                args.completion_marker.read_text(encoding="utf-8").splitlines(),
                ["alibaba"],
            )
            self.assertFalse(args.output.exists())
            self.assertFalse(args.public_output.exists())

    def test_failure_without_previous_catalog_has_no_valid_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root, None)
            args.providers = ["alibaba"]

            with mock.patch.object(
                update_china_clouds, "parse_args", return_value=args
            ), mock.patch.object(
                update_china_clouds,
                "fetch_provider",
                side_effect=RuntimeError("credentials rejected"),
            ), redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(update_china_clouds.main(), 1)

            self.assertIn("credentials rejected", stderr.getvalue())

            self.assertTrue(args.failure_marker.exists())
            self.assertFalse(args.completion_marker.exists())
            self.assertFalse(args.checkpoint.exists())
            self.assertFalse(args.output.exists())

    def test_completion_marker_appends_without_clearing_previous_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "provider-completed"
            marker.write_text("volcengine\n", encoding="utf-8")

            update_china_clouds.record_provider_completion(marker, "huawei")

            self.assertEqual(
                marker.read_text(encoding="utf-8").splitlines(),
                ["volcengine", "huawei"],
            )

    def test_unchanged_provider_still_records_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_path = root / "previous.json"
            self.write_catalog(previous_path, catalog())
            args = self.args(root, previous_path)
            args.providers = ["alibaba"]

            with mock.patch.object(
                update_china_clouds, "parse_args", return_value=args
            ), mock.patch.object(
                update_china_clouds,
                "fetch_provider",
                return_value=provider("alibaba", "old"),
            ):
                self.assertEqual(update_china_clouds.main(), 0)

            self.assertEqual(
                args.completion_marker.read_text(encoding="utf-8").splitlines(),
                ["alibaba"],
            )

    def test_worker_marks_explicit_failure_before_propagating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "provider-failed"
            with mock.patch.object(
                update_china_clouds,
                "fetch_provider",
                side_effect=RuntimeError("credentials rejected"),
            ):
                with self.assertRaisesRegex(RuntimeError, "credentials rejected"):
                    update_china_clouds.fetch_provider_guarded("alibaba", marker)
            self.assertTrue(marker.exists())

    def test_validate_only_never_calls_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            self.write_catalog(path, catalog())
            args = argparse.Namespace(validate_only=path)

            with mock.patch.object(
                update_china_clouds, "parse_args", return_value=args
            ), mock.patch.object(
                update_china_clouds, "fetch_provider"
            ) as fetch:
                self.assertEqual(update_china_clouds.main(), 0)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
