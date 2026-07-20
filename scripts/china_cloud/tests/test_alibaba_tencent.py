from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.china_cloud.providers import alibaba, tencent


REQUIRED_INSTANCE_KEYS = {
    "instanceType",
    "family",
    "familyName",
    "category",
    "vCPU",
    "memoryGiB",
    "architecture",
    "processor",
    "networkPerformance",
    "localStorage",
    "sourceUrl",
    "regions",
    "zones",
    "availableRegionCount",
    "availableZoneCount",
}


class AlibabaProviderTests(unittest.TestCase):
    def test_fetch_paginates_specs_and_collects_regional_stock(self) -> None:
        calls: list[tuple[str, str, dict[str, object]]] = []

        def fake_client(access_key: str, secret: str, region: str) -> str:
            self.assertEqual((access_key, secret), ("ali-id", "ali-secret"))
            return region

        def fake_invoke(
            client: str, action: str, **parameters: object
        ) -> dict[str, object]:
            calls.append((client, action, parameters))
            if action == "DescribeRegions":
                return {
                    "Regions": {
                        "Region": [
                            {"RegionId": "cn-a", "Status": "available"},
                            {"RegionId": "cn-b", "Status": "available"},
                        ]
                    }
                }
            if action == "DescribeInstanceTypes":
                if parameters.get("NextToken") == "page-2":
                    return {
                        "InstanceTypes": {
                            "InstanceType": [
                                {
                                    "InstanceTypeId": "ecs.gn7.large",
                                    "InstanceTypeFamily": "ecs.gn7",
                                    "CpuCoreCount": 4,
                                    "MemorySize": 16,
                                    "CpuArchitecture": "X86",
                                    "PhysicalProcessorModel": "Intel Xeon",
                                    "GPUAmount": 1,
                                    "GPUSpec": "NVIDIA A10",
                                }
                            ]
                        },
                        "NextToken": "",
                    }
                return {
                    "InstanceTypes": {
                        "InstanceType": [
                            {
                                "InstanceTypeId": "ecs.g8i.large",
                                "InstanceTypeFamily": "ecs.g8i",
                                "InstanceCategory": "generalPurpose",
                                "CpuCoreCount": 2,
                                "MemorySize": 8,
                                "CpuArchitecture": "X86",
                                "PhysicalProcessorModel": "Intel Xeon Platinum",
                                # Alibaba returns marketed Gbps in 1024-based
                                # kbit/s steps: 3 Gbps is 3,072,000 here.
                                "InstanceBandwidthRx": 3_072_000,
                                "InstanceBandwidthTx": 2_048_000,
                                "InstancePpsRx": 1_000_000,
                                "LocalStorageAmount": 2,
                                "LocalStorageCapacity": 100,
                                "LocalStorageCategory": "local_ssd",
                            }
                        ]
                    },
                    "NextToken": "page-2",
                }
            if action == "DescribeZones":
                zones = {
                    "cn-a": ["cn-a-a", "cn-a-b"],
                    "cn-b": ["cn-b-a"],
                }[client]
                return {"Zones": {"Zone": [{"ZoneId": zone} for zone in zones]}}
            if action == "DescribeAvailableResource":
                zone_id = "cn-a-a" if client == "cn-a" else "cn-b-a"
                supported = [
                    {
                        "Value": "ecs.g8i.large",
                        "Status": "Available",
                        "StatusCategory": "WithStock",
                    },
                    {
                        "Value": "ecs.gn7.large",
                        "Status": "SoldOut",
                        "StatusCategory": "WithoutStock",
                    },
                ]
                return {
                    "AvailableZones": {
                        "AvailableZone": [
                            {
                                "ZoneId": zone_id,
                                "Status": "Available",
                                "StatusCategory": "WithStock",
                                "AvailableResources": {
                                    "AvailableResource": [
                                        {
                                            "Type": "InstanceType",
                                            "SupportedResources": {
                                                "SupportedResource": supported
                                            },
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                }
            if action == "DescribePrice":
                self.assertEqual(client, "cn-a")
                return {
                    "PriceInfo": {
                        "Price": {
                            "Currency": "CNY",
                            "OriginalPrice": 0.55,
                            "DetailInfos": {
                                "DetailInfo": [
                                    {
                                        "Resource": "instanceType",
                                        "OriginalPrice": "0.4200",
                                    },
                                    {"Resource": "bandwidth", "OriginalPrice": 0},
                                ]
                            },
                        },
                    }
                }
            self.fail(f"unexpected Alibaba action: {action}")

        with (
            patch.object(
                alibaba,
                "require_env",
                return_value=("ali-id", "ali-secret"),
            ) as require_env,
            patch.object(alibaba, "_make_client", side_effect=fake_client),
            patch.object(alibaba, "_make_price_client", side_effect=fake_client),
            patch.object(alibaba, "_load_cached_prices", return_value={}),
            patch.object(alibaba, "_invoke", side_effect=fake_invoke),
        ):
            result = alibaba.fetch()

        require_env.assert_called_once_with(
            "ALIBABA_CLOUD_ACCESS_KEY_ID",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        )
        self.assertEqual(result["slug"], "alibaba")
        self.assertEqual(result["regionCount"], 2)
        self.assertEqual(result["zoneCount"], 3)
        by_type = {item["instanceType"]: item for item in result["instances"]}
        self.assertEqual(by_type["ecs.g8i.large"]["regions"], ["cn-a", "cn-b"])
        self.assertEqual(by_type["ecs.g8i.large"]["zones"], ["cn-a-a", "cn-b-a"])
        self.assertEqual(by_type["ecs.g8i.large"]["family"], "g8i")
        self.assertEqual(by_type["ecs.g8i.large"]["architecture"], "x86_64")
        self.assertEqual(
            by_type["ecs.g8i.large"]["networkPerformance"],
            "Up to 3 Gbps; 1 Mpps",
        )
        self.assertEqual(
            by_type["ecs.g8i.large"]["localStorage"],
            "2 x 100 GiB local_ssd",
        )
        self.assertEqual(
            by_type["ecs.g8i.large"]["onDemandPrices"],
            {
                "cn-a": {
                    "amount": "0.42",
                    "currency": "CNY",
                    "unit": "hour",
                }
            },
        )
        self.assertEqual(by_type["ecs.gn7.large"]["regions"], [])
        self.assertEqual(by_type["ecs.gn7.large"]["category"], "Accelerated computing")
        self.assertTrue(REQUIRED_INSTANCE_KEYS <= set(by_type["ecs.g8i.large"]))

        self.assertEqual(
            alibaba._network_performance(
                {"InstanceBandwidthRx": 81_920, "InstancePpsRx": 500_000}
            ),
            "Up to 80 Mbps; 500 Kpps",
        )

        spec_calls = [entry for entry in calls if entry[1] == "DescribeInstanceTypes"]
        self.assertEqual(len(spec_calls), 2)
        self.assertEqual(spec_calls[0][2], {"MaxResults": 100})
        self.assertEqual(
            spec_calls[1][2], {"MaxResults": 100, "NextToken": "page-2"}
        )
        self.assertEqual(
            {client for client, action, _ in calls if action == "DescribeZones"},
            {"cn-a", "cn-b"},
        )
        availability_calls = [
            entry for entry in calls if entry[1] == "DescribeAvailableResource"
        ]
        self.assertEqual(len(availability_calls), 2)
        self.assertTrue(
            all("IoOptimized" not in parameters for _, _, parameters in availability_calls)
        )
        price_calls = [entry for entry in calls if entry[1] == "DescribePrice"]
        self.assertEqual(
            price_calls,
            [
                (
                    "cn-a",
                    "DescribePrice",
                    {
                        "RegionId": "cn-a",
                        "ResourceType": "instance",
                        "InstanceType": "ecs.g8i.large",
                        "PriceUnit": "Hour",
                        "Period": 1,
                        "InstanceNetworkType": "vpc",
                        "InternetChargeType": "PayByTraffic",
                        "InternetMaxBandwidthOut": 0,
                        "SpotStrategy": "NoSpot",
                    },
                )
            ],
        )

    def test_price_enrichment_retains_real_cached_region_and_is_non_fatal(self) -> None:
        availability = {
            "ecs.c8i.large": {"regions": {"cn-a", "cn-b"}, "zones": set()},
            "ecs.g8i.large": {"regions": {"cn-b"}, "zones": set()},
            "ecs.offline.large": {"regions": set(), "zones": set()},
        }
        cached = {
            "ecs.c8i.large": {
                "cn-b": {"amount": "1.200", "currency": "CNY", "unit": "hour"},
                "cn-old": {"amount": "0.1", "currency": "CNY", "unit": "hour"},
            }
        }
        calls: list[tuple[str, str]] = []

        def fake_invoke(
            client: str, action: str, **parameters: object
        ) -> dict[str, object]:
            self.assertEqual(action, "DescribePrice")
            instance_type = str(parameters["InstanceType"])
            calls.append((instance_type, client))
            if instance_type == "ecs.g8i.large":
                raise RuntimeError("PriceNotFound")
            return {
                "PriceInfo": {
                    "Price": {"Currency": "CNY", "OriginalPrice": 1.1}
                }
            }

        with (
            patch.object(
                alibaba,
                "_make_price_client",
                side_effect=lambda _key, _secret, region: region,
            ),
            patch.object(alibaba, "_invoke", side_effect=fake_invoke),
        ):
            prices = alibaba._fetch_on_demand_prices(
                "ali-id",
                "ali-secret",
                availability,
                cached_prices=cached,
                time_budget_seconds=2,
                queries_per_second=10_000,
                workers=2,
                day_ordinal=1,
            )

        self.assertEqual(set(calls), {("ecs.c8i.large", "cn-a"), ("ecs.g8i.large", "cn-b")})
        self.assertEqual(
            prices,
            {
                "ecs.c8i.large": {
                    "cn-a": {
                        "amount": "1.1",
                        "currency": "CNY",
                        "unit": "hour",
                    },
                    "cn-b": {
                        "amount": "1.2",
                        "currency": "CNY",
                        "unit": "hour",
                    }
                }
            },
        )

    def test_extract_price_requires_positive_supported_currency_original_amount(self) -> None:
        self.assertEqual(
            alibaba._extract_on_demand_price(
                {
                    "PriceInfo": {
                        "Price": {
                            "Currency": "CNY",
                            "OriginalPrice": 10,
                            "DetailInfos": {
                                "DetailInfo": [
                                    {"Resource": "systemDisk", "OriginalPrice": 9},
                                    {
                                        "Resource": "instanceType",
                                        "OriginalPrice": "1.2500",
                                    },
                                ]
                            },
                        },
                    }
                }
            ),
            {"amount": "1.25", "currency": "CNY", "unit": "hour"},
        )
        self.assertEqual(
            alibaba._extract_on_demand_price(
                {"PriceInfo": {"Price": {"Currency": "USD", "OriginalPrice": 1}}}
            ),
            {"amount": "1", "currency": "USD", "unit": "hour"},
        )
        self.assertEqual(alibaba._amount_string(10), "10")

    def test_repeated_pagination_token_fails_instead_of_truncating(self) -> None:
        with patch.object(
            alibaba,
            "_invoke",
            return_value={"InstanceTypes": {"InstanceType": []}, "NextToken": "same"},
        ):
            with self.assertRaisesRegex(RuntimeError, "repeated NextToken"):
                alibaba._fetch_instance_types(object())


class TencentProviderTests(unittest.TestCase):
    def test_uses_lowest_public_hourly_price_across_zones(self) -> None:
        prices = tencent._regional_on_demand_prices(
            [
                {
                    "Zone": "ap-a-1",
                    "InstanceType": "SA2.MEDIUM4",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {
                        "UnitPrice": "0.4200",
                        "UnitPriceDiscount": 0.21,
                        "ChargeUnit": "HOUR",
                    },
                },
                {
                    "Zone": "ap-a-2",
                    "InstanceType": "SA2.MEDIUM4",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {
                        "UnitPrice": 0.37,
                        "UnitPriceDiscount": 0.18,
                        "ChargeUnit": "hour",
                    },
                },
                {
                    "Zone": "ap-a-3",
                    "InstanceType": "SA2.MEDIUM4",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {
                        "UnitPrice": 0,
                        "OriginalPrice": 59,
                        "ChargeUnit": "HOUR",
                    },
                },
                {
                    "Zone": "ap-a-1",
                    "InstanceType": "MA2.MEDIUM8",
                    "Status": "SELL",
                    "StatusCategory": "EnoughStock",
                    "Price": {"UnitPrice": 8, "ChargeUnit": "GB"},
                },
                {
                    "Zone": "ap-a-1",
                    "InstanceType": "SOLD.OUT",
                    "Status": "SOLD_OUT",
                    "StatusCategory": "WithoutStock",
                    "Price": {"UnitPrice": 1, "ChargeUnit": "HOUR"},
                },
            ],
            "ap-a",
        )

        self.assertEqual(
            prices,
            {
                "SA2.MEDIUM4": {
                    "ap-a": {
                        "amount": "0.37",
                        "currency": "CNY",
                        "unit": "hour",
                    }
                }
            },
        )

    def test_fetch_enumerates_every_region_and_merges_zone_availability(self) -> None:
        calls: list[tuple[object, str, dict[str, object]]] = []

        def fake_call(
            client: object,
            models_module: str,
            request_class: str,
            method: str,
            **parameters: object,
        ) -> dict[str, object]:
            del models_module, request_class
            calls.append((client, method, parameters))
            if method == "DescribeRegions":
                return {
                    "RegionSet": [
                        {"Region": "ap-a", "RegionState": "AVAILABLE"},
                        {"Region": "ap-b"},
                        {"Region": "ap-disabled", "RegionState": "UNAVAILABLE"},
                    ]
                }
            region = str(client)
            if method == "DescribeZones":
                zones = {
                    "ap-a": [
                        {"Zone": "ap-a-1", "ZoneState": "AVAILABLE"},
                        {"Zone": "ap-a-2"},
                        {"Zone": "ap-a-retired", "ZoneState": "UNAVAILABLE"},
                    ],
                    "ap-b": [
                        {"Zone": "ap-b-1"},
                        {"Zone": "ap-b-retired", "ZoneState": "UNAVAILABLE"},
                    ],
                }[region]
                return {"ZoneSet": zones}
            if method == "DescribeInstanceTypeConfigs":
                zone = "ap-a-1" if region == "ap-a" else "ap-b-1"
                configs: list[dict[str, object]] = [
                    {
                        "Zone": zone,
                        "InstanceType": "SA2.MEDIUM4",
                        "InstanceFamily": "SA2",
                        "CPU": 2,
                        "Memory": 4,
                        "GPU": 0,
                    }
                ]
                if region == "ap-a":
                    configs.append(
                        {
                            "Zone": "ap-a-2",
                            "InstanceType": "GN7.2XLARGE8",
                            "InstanceFamily": "GN7",
                            "CPU": 8,
                            "Memory": 32,
                            "GPU": 1,
                            "GpuCount": 1,
                        }
                    )
                return {"InstanceTypeConfigSet": configs}
            if method == "DescribeZoneInstanceConfigInfos":
                zone = "ap-a-1" if region == "ap-a" else "ap-b-1"
                quotas: list[dict[str, object]] = [
                    {
                        "Zone": zone,
                        "InstanceType": "SA2.MEDIUM4",
                        "InstanceFamily": "SA2",
                        "TypeName": "Standard SA2",
                        "Cpu": 2,
                        "Memory": 4,
                        "Status": "SELL",
                        "StatusCategory": "EnoughStock",
                        "CpuType": "AMD EPYC",
                        "Frequency": 2.6,
                        "InstanceBandwidth": 3,
                        "InstancePps": 30,
                        "Price": {
                            "UnitPrice": 0.42 if region == "ap-a" else 0.45,
                            "UnitPriceDiscount": 0.21,
                            "ChargeUnit": "HOUR",
                        },
                    }
                ]
                if region == "ap-a":
                    quotas.extend(
                        [
                            {
                                "Zone": "ap-a-2",
                                "InstanceType": "GN7.2XLARGE8",
                                "InstanceFamily": "GN7",
                                "Cpu": 8,
                                "Memory": 32,
                                "GpuCount": 1,
                                "Status": "SOLD_OUT",
                                "StatusCategory": "WithoutStock",
                            },
                            {
                                "Zone": "ap-a-2",
                                "InstanceType": "MA2.MEDIUM8",
                                "InstanceFamily": "MA2",
                                "TypeName": "Memory optimized MA2",
                                "Cpu": 2,
                                "Memory": 8,
                                "Status": "SELL",
                                "StatusCategory": "NormalStock",
                                "LocalDiskTypeList": [
                                    {
                                        "Type": "LOCAL_SSD",
                                        "MinSize": 100,
                                        "MaxSize": 200,
                                    }
                                ],
                                "StorageBlockAmount": 1,
                            },
                        ]
                    )
                return {"InstanceTypeQuotaSet": quotas}
            self.fail(f"unexpected Tencent method: {method}")

        with (
            patch.object(
                tencent,
                "require_env",
                return_value=("tencent-id", "tencent-key"),
            ) as require_env,
            patch.object(tencent, "_make_region_client", return_value="regions"),
            patch.object(
                tencent,
                "_make_cvm_client",
                side_effect=lambda secret_id, secret_key, region: region,
            ) as make_cvm_client,
            patch.object(tencent, "_call", side_effect=fake_call),
            patch.object(
                tencent,
                "provider_result",
                wraps=tencent.provider_result,
            ) as provider_result,
        ):
            result = tencent.fetch()

        require_env.assert_called_once_with(
            "TENCENTCLOUD_SECRET_ID",
            "TENCENTCLOUD_SECRET_KEY",
        )
        self.assertEqual(
            make_cvm_client.call_args_list[0].args,
            ("tencent-id", "tencent-key", "ap-a"),
        )
        self.assertEqual(
            [call.args[2] for call in make_cvm_client.call_args_list],
            ["ap-a", "ap-b"],
        )
        self.assertEqual(result["slug"], "tencent")
        self.assertEqual(result["regionCount"], 2)
        self.assertEqual(result["zoneCount"], 3)
        by_type = {item["instanceType"]: item for item in result["instances"]}
        standard = by_type["SA2.MEDIUM4"]
        self.assertEqual(standard["regions"], ["ap-a", "ap-b"])
        self.assertEqual(standard["zones"], ["ap-a-1", "ap-b-1"])
        self.assertEqual(standard["architecture"], "x86_64")
        self.assertEqual(standard["processor"], "AMD EPYC @ 2.6 GHz")
        self.assertEqual(
            standard["networkPerformance"], "Up to 3 Gbps; 300 Kpps"
        )
        raw_records = provider_result.call_args.args[1]
        raw_standard_prices: dict[str, object] = {}
        for record in raw_records:
            if record["instanceType"] == "SA2.MEDIUM4":
                raw_standard_prices.update(record.get("onDemandPrices", {}))
        self.assertEqual(
            raw_standard_prices,
            {
                "ap-a": {"amount": "0.42", "currency": "CNY", "unit": "hour"},
                "ap-b": {"amount": "0.45", "currency": "CNY", "unit": "hour"},
            },
        )
        self.assertEqual(by_type["GN7.2XLARGE8"]["regions"], [])
        self.assertEqual(by_type["GN7.2XLARGE8"]["category"], "Accelerated computing")
        self.assertEqual(by_type["MA2.MEDIUM8"]["regions"], ["ap-a"])
        self.assertEqual(
            by_type["MA2.MEDIUM8"]["localStorage"],
            "1 x LOCAL_SSD 100-200 GiB",
        )
        self.assertTrue(REQUIRED_INSTANCE_KEYS <= set(standard))

        region_call = next(entry for entry in calls if entry[1] == "DescribeRegions")
        self.assertEqual(region_call[2], {"Product": "cvm", "Scene": 1})
        spec_calls = [entry for entry in calls if entry[1] == "DescribeInstanceTypeConfigs"]
        self.assertEqual(len(spec_calls), 2)
        self.assertTrue(all(parameters == {} for _, _, parameters in spec_calls))
        quota_calls = [
            entry for entry in calls if entry[1] == "DescribeZoneInstanceConfigInfos"
        ]
        self.assertEqual(len(quota_calls), 2)
        self.assertEqual(
            quota_calls[0][2],
            {
                "Filters": [
                    {
                        "Name": "instance-charge-type",
                        "Values": ["POSTPAID_BY_HOUR"],
                    }
                ]
            },
        )
        self.assertNotIn("Offset", quota_calls[0][2])
        self.assertNotIn("Limit", quota_calls[0][2])


if __name__ == "__main__":
    unittest.main()
