from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.china_cloud.providers import tencent


class TencentCostExtractionTests(unittest.TestCase):
    def test_subscription_uses_lowest_public_one_year_total(self) -> None:
        prices = tencent._regional_subscription_prices(
            [
                {
                    "Zone": "ap-test-1",
                    "InstanceType": "S.TEST",
                    "InstanceChargeType": "PREPAID",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {
                        "OriginalPriceOneYear": "876.00",
                        "DiscountPriceOneYear": "8.76",
                        "DiscountOneYear": 1,
                    },
                },
                {
                    "Zone": "ap-test-2",
                    "InstanceType": "S.TEST",
                    "InstanceChargeType": "PREPAID",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {
                        "OriginalPriceOneYear": 1752,
                        "DiscountPriceOneYear": 1,
                    },
                },
                {
                    "Zone": "ap-test-3",
                    "InstanceType": "S.TEST",
                    "InstanceChargeType": "PREPAID",
                    "Status": "SOLD_OUT",
                    "StatusCategory": "WithoutStock",
                    "Price": {"OriginalPriceOneYear": 1},
                },
                {
                    "Zone": "ap-test-1",
                    "InstanceType": "WRONG.MODE",
                    "InstanceChargeType": "SPOTPAID",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {"OriginalPriceOneYear": 100},
                },
            ],
            "ap-test",
        )

        self.assertEqual(
            prices,
            {
                "S.TEST": {
                    "ap-test": {
                        "amount": "0.1",
                        "totalAmount": "876",
                        "currency": "CNY",
                        "unit": "hour",
                        "term": "1-year",
                        "payment": "all-upfront",
                    }
                }
            },
        )

        postpaid_prices = tencent._regional_subscription_prices(
            [
                {
                    "InstanceType": "S.TEST",
                    "InstanceChargeType": "POSTPAID_BY_HOUR",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {"OriginalPriceOneYear": "876"},
                }
            ],
            "ap-test",
        )
        self.assertEqual(postpaid_prices, {})

    def test_spot_uses_lowest_public_hourly_price_and_reports_zone(self) -> None:
        prices = tencent._regional_spot_prices(
            [
                {
                    "Zone": "ap-test-1",
                    "InstanceType": "S.TEST",
                    "InstanceChargeType": "SPOTPAID",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {
                        "UnitPrice": "0.0800",
                        "UnitPriceDiscount": "0.0001",
                        "ChargeUnit": "HOUR",
                    },
                },
                {
                    "Zone": "ap-test-2",
                    "InstanceType": "S.TEST",
                    "InstanceChargeType": "SPOTPAID",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {
                        "UnitPrice": "0.0400",
                        "UnitPriceDiscount": "0.0002",
                        "ChargeUnit": "HOUR",
                    },
                },
                {
                    "Zone": "ap-test-3",
                    "InstanceType": "S.TEST",
                    "InstanceChargeType": "SPOTPAID",
                    "Status": "SOLD_OUT",
                    "StatusCategory": "WithoutStock",
                    "Price": {"UnitPrice": 0.001, "ChargeUnit": "HOUR"},
                },
                {
                    "Zone": "ap-test-1",
                    "InstanceType": "WRONG.MODE",
                    "InstanceChargeType": "PREPAID",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {"UnitPrice": 0.01, "ChargeUnit": "HOUR"},
                },
            ],
            "ap-test",
        )

        self.assertEqual(
            prices,
            {
                "S.TEST": {
                    "ap-test": {
                        "amount": "0.0001",
                        "currency": "CNY",
                        "unit": "hour",
                        "zone": "ap-test-1",
                    }
                }
            },
        )


class TencentCostFetchTests(unittest.TestCase):
    def test_fetch_requests_each_public_charge_type_and_emits_region_maps(
        self,
    ) -> None:
        charge_type_calls: list[tuple[str, ...]] = []

        def fake_call(
            client: object,
            models_module: str,
            request_class: str,
            method: str,
            **parameters: object,
        ) -> dict[str, object]:
            del client, models_module, request_class
            if method == "DescribeRegions":
                return {
                    "RegionSet": [
                        {"Region": "ap-test", "RegionState": "AVAILABLE"}
                    ]
                }
            if method == "DescribeZones":
                return {
                    "ZoneSet": [
                        {"Zone": "ap-test-1", "ZoneState": "AVAILABLE"}
                    ]
                }
            if method == "DescribeInstanceTypeConfigs":
                return {
                    "InstanceTypeConfigSet": [
                        {
                            "Zone": "ap-test-1",
                            "InstanceType": "S.TEST",
                            "InstanceFamily": "S",
                            "CPU": 2,
                            "Memory": 4,
                        }
                    ]
                }
            if method == "DescribeZoneInstanceConfigInfos":
                filters = parameters["Filters"]
                self.assertIsInstance(filters, list)
                charge_types = tuple(filters[0]["Values"])  # type: ignore[index]
                charge_type_calls.append(charge_types)
                prices = {
                    "POSTPAID_BY_HOUR": {
                        "UnitPrice": 0.4,
                        "UnitPriceDiscount": 0.2,
                        "ChargeUnit": "HOUR",
                    },
                    "PREPAID": {
                        "OriginalPriceOneYear": 876,
                        "DiscountPriceOneYear": 1,
                    },
                    "SPOTPAID": {
                        "UnitPrice": 0.04,
                        "UnitPriceDiscount": 0.001,
                        "ChargeUnit": "HOUR",
                    },
                }
                return {
                    "InstanceTypeQuotaSet": [
                        {
                            "Zone": "ap-test-1",
                            "InstanceType": "S.TEST",
                            "InstanceFamily": "S",
                            "TypeName": "Standard test",
                            "Cpu": 2,
                            "Memory": 4,
                            "Status": "SELL",
                            "StatusCategory": "EnoughStock",
                            "InstanceChargeType": charge_type,
                            "Price": prices[charge_type],
                        }
                        for charge_type in charge_types
                    ]
                }
            self.fail(f"unexpected Tencent method: {method}")

        with (
            patch.object(tencent, "require_env", return_value=("id", "key")),
            patch.object(tencent, "_make_region_client", return_value=object()),
            patch.object(tencent, "_make_cvm_client", return_value=object()),
            patch.object(tencent, "_call", side_effect=fake_call),
        ):
            result = tencent.fetch()

        self.assertEqual(
            charge_type_calls,
            [("POSTPAID_BY_HOUR",), ("PREPAID", "SPOTPAID")],
        )
        instance = result["instances"][0]
        self.assertEqual(
            instance["onDemandPrices"],
            {
                "ap-test": {
                    "amount": "0.4",
                    "currency": "CNY",
                    "unit": "hour",
                }
            },
        )
        self.assertEqual(
            instance["subscriptionPrices"],
            {
                "ap-test": {
                    "amount": "0.1",
                    "totalAmount": "876",
                    "currency": "CNY",
                    "unit": "hour",
                    "term": "1-year",
                    "payment": "all-upfront",
                }
            },
        )
        self.assertEqual(
            instance["spotPrices"],
            {
                "ap-test": {
                    "amount": "0.001",
                    "currency": "CNY",
                    "unit": "hour",
                    "zone": "ap-test-1",
                }
            },
        )

    def test_optional_pricing_error_is_non_fatal(self) -> None:
        with (
            patch.object(
                tencent,
                "_call",
                side_effect=RuntimeError("regional price mode unavailable"),
            ),
            patch.object(tencent, "log_progress"),
        ):
            quotas = tencent._fetch_charge_type_quotas(
                object(), "ap-test", "SPOTPAID"
            )

        self.assertEqual(quotas, [])


if __name__ == "__main__":
    unittest.main()
