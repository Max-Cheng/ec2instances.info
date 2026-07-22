from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts.china_cloud.providers import alibaba


class AlibabaExtendedPriceTests(unittest.TestCase):
    def test_subscription_uses_public_original_total_and_converts_to_hourly(self) -> None:
        price = alibaba._extract_subscription_price(
            {
                "PriceInfo": {
                    "Price": {
                        "Currency": "CNY",
                        "OriginalPrice": 9999,
                        "TradePrice": 1,
                        "DiscountPrice": 9998,
                        "DetailInfos": {
                            "DetailInfo": [
                                {
                                    "Resource": "instanceType",
                                    "OriginalPrice": "876.00",
                                    "TradePrice": "438.00",
                                },
                                {"Resource": "bandwidth", "OriginalPrice": 0},
                            ]
                        },
                    }
                }
            }
        )

        self.assertEqual(
            price,
            {
                "amount": "0.1",
                "totalAmount": "876",
                "currency": "CNY",
                "unit": "hour",
                "term": "1-year",
                "payment": "all-upfront",
            },
        )
        self.assertIsNone(
            alibaba._extract_subscription_price(
                {
                    "PriceInfo": {
                        "Price": {"Currency": "EUR", "OriginalPrice": 876}
                    }
                }
            )
        )

    def test_spot_uses_current_spot_trade_price_not_regular_list_price(self) -> None:
        price = alibaba._extract_spot_price(
            {
                "PriceInfo": {
                    "Price": {
                        "Currency": "CNY",
                        "OriginalPrice": "0.8",
                        "TradePrice": "0.2",
                    }
                }
            },
            zone="cn-a-b",
            observed_at=datetime(2026, 7, 22, 10, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(
            price,
            {
                "amount": "0.2",
                "currency": "CNY",
                "unit": "hour",
                "observedAt": "2026-07-22T10:30:00Z",
                "zone": "cn-a-b",
            },
        )

    def test_fetches_prepaid_list_total_and_current_spot_with_bounded_clients(self) -> None:
        calls: list[tuple[str, str, dict[str, object]]] = []
        now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)

        def fake_invoke(
            client: str, action: str, **parameters: object
        ) -> dict[str, object]:
            calls.append((client, action, parameters))
            if action == "DescribePrice" and parameters.get("SpotStrategy"):
                return {
                    "PriceInfo": {
                        "Price": {
                            "Currency": "CNY",
                            "OriginalPrice": 0.7,
                            "TradePrice": 0.4,
                        }
                    }
                }
            if action == "DescribePrice":
                return {
                    "PriceInfo": {
                        "Price": {
                            "Currency": "CNY",
                            "OriginalPrice": 8760,
                            "TradePrice": 4380,
                        }
                    }
                }
            self.fail(f"unexpected action: {action}")

        with (
            patch.object(
                alibaba,
                "_make_price_client",
                side_effect=lambda _key, _secret, region: region,
            ),
            patch.object(alibaba, "_invoke", side_effect=fake_invoke),
        ):
            subscription, spot = alibaba._fetch_extended_prices(
                "ali-id",
                "ali-secret",
                {
                    "ecs.g8i.large": {
                        "regions": {"cn-a"},
                        "zones": {"cn-a-a", "cn-a-b"},
                    }
                },
                cached_subscription_prices={
                    "ecs.g8i.large": {
                        "cn-a": {
                            "amount": "0.5",
                            "totalAmount": "4380",
                            "currency": "CNY",
                            "unit": "hour",
                            "term": "1-year",
                            "payment": "all-upfront",
                        }
                    }
                },
                time_budget_seconds=2,
                queries_per_second=10_000,
                workers=1,
                day_ordinal=1,
                now=now,
            )

        self.assertEqual(
            subscription,
            {
                "ecs.g8i.large": {
                    "cn-a": {
                        "amount": "1",
                        "totalAmount": "8760",
                        "currency": "CNY",
                        "unit": "hour",
                        "term": "1-year",
                        "payment": "all-upfront",
                    }
                }
            },
        )
        self.assertEqual(
            spot,
            {
                "ecs.g8i.large": {
                    "cn-a": {
                        "amount": "0.4",
                        "currency": "CNY",
                        "unit": "hour",
                        "observedAt": "2026-07-22T12:00:00Z",
                        "zone": "cn-a-b",
                    }
                }
            },
        )
        self.assertEqual(
            calls,
            [
                (
                    "cn-a",
                    "DescribePrice",
                    {
                        "RegionId": "cn-a",
                        "ResourceType": "instance",
                        "InstanceType": "ecs.g8i.large",
                        "PriceUnit": "Year",
                        "Period": 1,
                        "InstanceNetworkType": "vpc",
                        "InternetChargeType": "PayByTraffic",
                        "InternetMaxBandwidthOut": 0,
                    },
                ),
                (
                    "cn-a",
                    "DescribePrice",
                    {
                        "RegionId": "cn-a",
                        "ZoneId": "cn-a-b",
                        "ResourceType": "instance",
                        "InstanceType": "ecs.g8i.large",
                        "PriceUnit": "Hour",
                        "Period": 1,
                        "SpotStrategy": "SpotAsPriceGo",
                        "SpotDuration": 1,
                        "InstanceNetworkType": "vpc",
                        "IoOptimized": "optimized",
                        "InternetChargeType": "PayByTraffic",
                        "InternetMaxBandwidthOut": 0,
                    },
                ),
            ],
        )

    def test_stale_spot_cache_is_dropped_and_extended_fields_are_reattached(self) -> None:
        now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
        self.assertEqual(
            alibaba._clean_cached_spot_price_map(
                {
                    "cn-a": {
                        "amount": "0.4",
                        "currency": "CNY",
                        "unit": "hour",
                        "observedAt": "2026-07-20T12:00:00Z",
                        "zone": "cn-a-a",
                    }
                },
                now=now,
            ),
            {},
        )

        result = {
            "instances": [
                {"instanceType": "ecs.g8i.large", "regions": ["cn-a"]}
            ]
        }
        alibaba._attach_extended_prices(
            result,
            {
                "ecs.g8i.large": {
                    "cn-a": {"amount": "1"},
                    "cn-removed": {"amount": "2"},
                }
            },
            {"ecs.g8i.large": {"cn-a": {"amount": "0.4"}}},
        )
        self.assertEqual(
            result["instances"][0],
            {
                "instanceType": "ecs.g8i.large",
                "regions": ["cn-a"],
                "subscriptionPrices": {"cn-a": {"amount": "1"}},
                "spotPrices": {"cn-a": {"amount": "0.4"}},
            },
        )


if __name__ == "__main__":
    unittest.main()
