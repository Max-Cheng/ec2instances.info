from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.china_cloud.providers import volcengine


class Request(SimpleNamespace):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)


class FakeEcs:
    DescribeAvailableResourceRequest = Request
    DescribeInstanceTypesRequest = Request
    DescribeRegionsRequest = Request
    DescribeZonesRequest = Request


def ns(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


class BeijingClient:
    def __init__(self) -> None:
        self.region_tokens: list[str | None] = []
        self.instance_tokens: list[str | None] = []
        self.availability_requests: list[Request] = []

    def describe_regions(self, request: Request) -> SimpleNamespace:
        self.region_tokens.append(request.next_token)
        self.assert_request_size(request.max_results, 20)
        if request.next_token is None:
            return ns(regions=[ns(region_id="cn-beijing")], next_token="regions-2")
        return ns(regions=[{"RegionId": "cn-shanghai"}], next_token=None)

    def describe_instance_types(self, request: Request) -> SimpleNamespace:
        self.instance_tokens.append(request.next_token)
        self.assert_request_size(request.max_results, 1000)
        if request.next_token is None:
            return ns(
                instance_types=[
                    ns(
                        instance_type_id="ecs.g3i.large",
                        instance_type_family="ecs.g3i",
                        processor=ns(cpus=2, model="Intel Xeon Ice Lake"),
                        memory=ns(size=8192),
                        network=ns(
                            baseline_bandwidth_mbps=2000,
                            maximum_bandwidth_mbps=4000,
                            maximum_throughput_kpps=500,
                        ),
                        local_volumes=[],
                        gpu=None,
                    )
                ],
                next_token="types-2",
            )
        return ns(
            instance_types=[
                {
                    "InstanceTypeId": "ecs.g3i.large",
                    "InstanceTypeFamily": "ecs.g3i",
                    "Processor": {"Cpus": 2, "Model": "Intel Xeon Ice Lake"},
                    "Memory": {"Size": 8192},
                    "Network": {"MaximumBandwidthMbps": 4000},
                    "LocalVolumes": [],
                },
                ns(
                    instance_type_id="ecs.gpu3a.xlarge",
                    instance_type_family="ecs.gpu3a",
                    processor=ns(cpus=4, model="Ampere Altra Neoverse"),
                    memory=ns(size=16384),
                    network=ns(maximum_bandwidth_mbps=10000),
                    local_volumes=[ns(count=2, size=1900, volume_type="NVMe SSD")],
                    gpu=ns(
                        gpu_devices=[ns(count=2, product_name="NVIDIA A10")]
                    ),
                ),
            ],
            next_token="",
        )

    def describe_zones(self, request: Request) -> SimpleNamespace:
        del request
        return ns(zones=[ns(zone_id="cn-beijing-a"), ns(zone_id="cn-beijing-b")])

    def describe_available_resource(self, request: Request) -> SimpleNamespace:
        self.availability_requests.append(request)
        return ns(
            available_zones=[
                ns(
                    region_id="cn-beijing",
                    zone_id="cn-beijing-a",
                    status="Available",
                    available_resources=[
                        ns(
                            type="InstanceType",
                            supported_resources=[
                                ns(status="Available", value="ecs.g3i.large"),
                                ns(status="SoldOut", value="ecs.gpu3a.xlarge"),
                            ],
                        )
                    ],
                ),
                ns(
                    region_id="cn-beijing",
                    zone_id="cn-beijing-b",
                    status="SoldOut",
                    available_resources=[
                        ns(
                            type="InstanceType",
                            supported_resources=[
                                ns(status="Available", value="ecs.gpu3a.xlarge")
                            ],
                        )
                    ],
                ),
            ]
        )

    @staticmethod
    def assert_request_size(actual: int, expected: int) -> None:
        if actual != expected:
            raise AssertionError(f"expected page size {expected}, got {actual}")


class ShanghaiClient:
    def __init__(self) -> None:
        self.availability_requests: list[Request] = []

    def describe_zones(self, request: Request) -> dict[str, object]:
        del request
        return {"Zones": [{"ZoneId": "cn-shanghai-a"}]}

    def describe_available_resource(self, request: Request) -> dict[str, object]:
        self.availability_requests.append(request)
        return {
            "AvailableZones": [
                {
                    "RegionId": "cn-shanghai",
                    "ZoneId": "cn-shanghai-a",
                    "Status": "Available",
                    "AvailableResources": [
                        {
                            "Type": "InstanceType",
                            "SupportedResources": [
                                {"Status": "Available", "Value": "ecs.g3i.large"},
                                {
                                    "Status": "Available",
                                    "Value": "ecs.gpu3a.xlarge",
                                },
                            ],
                        },
                        {
                            "Type": "VolumeType",
                            "SupportedResources": [
                                {"Status": "Available", "Value": "ESSD_PL0"}
                            ],
                        },
                    ],
                }
            ]
        }


class VolcengineProviderTest(unittest.TestCase):
    def test_fetch_paginates_deduplicates_and_merges_availability(self) -> None:
        beijing = BeijingClient()
        shanghai = ShanghaiClient()
        clients = {
            "cn-beijing": beijing,
            "cn-shanghai": shanghai,
        }
        created_regions: list[str] = []

        def fake_client(
            core: object,
            ecs: object,
            access_key: str,
            secret_key: str,
            region: str,
        ) -> object:
            del core, ecs
            self.assertEqual(access_key, "test-ak")
            self.assertEqual(secret_key, "test-sk")
            created_regions.append(region)
            return clients[region]

        with (
            patch.dict(
                os.environ,
                {
                    "VOLCENGINE_ACCESS_KEY_ID": "test-ak",
                    "VOLCENGINE_SECRET_ACCESS_KEY": "test-sk",
                },
                clear=True,
            ),
            patch.object(volcengine, "_sdk", return_value=(object(), FakeEcs)),
            patch.object(volcengine, "_client", side_effect=fake_client),
        ):
            result = volcengine.fetch()

        self.assertEqual(result["slug"], "volcengine")
        self.assertEqual(result["regionCount"], 2)
        self.assertEqual(result["zoneCount"], 3)
        self.assertEqual(created_regions, ["cn-beijing", "cn-shanghai"])
        self.assertEqual(beijing.region_tokens, [None, "regions-2"])
        self.assertEqual(beijing.instance_tokens, [None, "types-2"])

        instances = {item["instanceType"]: item for item in result["instances"]}
        self.assertEqual(set(instances), {"ecs.g3i.large", "ecs.gpu3a.xlarge"})

        general = instances["ecs.g3i.large"]
        self.assertEqual(general["family"], "g3i")
        self.assertEqual(general["vCPU"], 2)
        self.assertEqual(general["memoryGiB"], 8)
        self.assertEqual(general["architecture"], "x86_64")
        self.assertEqual(
            general["regions"], ["cn-beijing", "cn-shanghai"]
        )
        self.assertEqual(
            general["zones"], ["cn-beijing-a", "cn-shanghai-a"]
        )
        self.assertEqual(general["availableRegionCount"], 2)
        self.assertEqual(general["availableZoneCount"], 2)
        self.assertIn("2 Gbps baseline / 4 Gbps maximum", general["networkPerformance"])

        gpu = instances["ecs.gpu3a.xlarge"]
        self.assertEqual(gpu["architecture"], "arm64")
        self.assertEqual(gpu["category"], "Accelerated computing")
        self.assertEqual(gpu["localStorage"], "2 x 1900 GiB NVMe SSD")
        self.assertEqual(gpu["regions"], ["cn-shanghai"])
        self.assertEqual(gpu["zones"], ["cn-shanghai-a"])

        for request in (
            beijing.availability_requests + shanghai.availability_requests
        ):
            self.assertEqual(request.destination_resource, "InstanceType")
            self.assertEqual(request.instance_charge_type, "PostPaid")
            self.assertEqual(request.spot_strategy, "NoSpot")

    def test_missing_credentials_stops_before_loading_sdk(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"VOLCENGINE_ACCESS_KEY_ID": "test-ak"},
                clear=True,
            ),
            patch.object(volcengine, "_sdk") as sdk,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "VOLCENGINE_SECRET_ACCESS_KEY",
            ):
                volcengine.fetch()
        sdk.assert_not_called()

    def test_repeated_instance_page_token_is_rejected(self) -> None:
        client = SimpleNamespace(
            describe_instance_types=lambda request: ns(
                instance_types=[],
                next_token="same-token",
            )
        )
        with self.assertRaisesRegex(RuntimeError, "repeated NextToken"):
            volcengine._paginated_instance_types(client, FakeEcs)


if __name__ == "__main__":
    unittest.main()
