from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from scripts.china_cloud.providers import huawei


class FakeRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


FAKE_SDK = SimpleNamespace(
    KeystoneListRegionsRequest=FakeRequest,
    KeystoneListAuthProjectsRequest=FakeRequest,
    ListFlavorsRequest=FakeRequest,
    ListServerAzInfoRequest=FakeRequest,
)


def flavor(
    instance_type: str,
    *,
    vcpus: str = "4",
    ram: int = 16384,
    extra: dict | None = None,
    public: bool = True,
    disabled: bool = False,
):
    return SimpleNamespace(
        id=instance_type,
        name=instance_type,
        vcpus=vcpus,
        ram=ram,
        os_extra_specs=extra or {},
        os_flavor_accessis_public=public,
        os_flv_disable_ddisabled=disabled,
    )


class FakeIamClient:
    def __init__(self, regions, projects):
        self.regions = regions
        self.projects = projects

    def keystone_list_regions(self, _request):
        return SimpleNamespace(regions=self.regions)

    def keystone_list_auth_projects(self, _request):
        return SimpleNamespace(projects=self.projects)


class FakeEcsClient:
    def __init__(self, zones, pages, *, zone_error=None):
        self.zones = zones
        self.pages = pages
        self.zone_error = zone_error
        self.markers = []

    def list_server_az_info(self, _request):
        if self.zone_error is not None:
            raise self.zone_error
        return SimpleNamespace(
            availability_zones=[
                (
                    SimpleNamespace(availability_zone_id=zone)
                    if isinstance(zone, str)
                    else zone
                )
                for zone in self.zones
            ]
        )

    def list_flavors(self, request):
        self.markers.append(getattr(request, "marker", None))
        return SimpleNamespace(flavors=self.pages[len(self.markers) - 1])


class FakeClientRequestException(Exception):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.status_code = 403
        self.error_code = error_code


class HuaweiProviderTest(unittest.TestCase):
    def test_list_zone_ids_only_keeps_public_shared_center_zones(self):
        zones = [
            SimpleNamespace(
                availability_zone_id="cn-north-4a",
                type="Center",
                mode="shared",
                category=0,
            ),
            SimpleNamespace(
                availability_zone_id="cn-north-4-edge",
                type="Edge",
                mode="shared",
                category=0,
            ),
            SimpleNamespace(
                availability_zone_id="cn-north-4-dedicated",
                type="Center",
                mode="dedicated",
                category=0,
            ),
            SimpleNamespace(
                availability_zone_id="cn-north-4-homezone",
                type="Center",
                mode="shared",
                category=21,
            ),
            SimpleNamespace(
                availability_zone_id="cn-north-4-ies",
                type="Center",
                mode="shared",
                category=41,
            ),
            # Legacy responses omitted all three classification fields.
            SimpleNamespace(availability_zone_id="cn-north-4-legacy"),
            # Default-valued classifiers can be omitted by some regions.
            SimpleNamespace(
                availability_zone_id="cn-north-4-incomplete",
                type="Center",
                mode="shared",
            ),
            SimpleNamespace(
                availability_zone_id="cn-north-4-no-type",
                mode="shared",
                category=0,
            ),
            SimpleNamespace(
                availability_zone_id="cn-north-4-no-mode",
                type="Center",
                category=0,
            ),
        ]
        client = FakeEcsClient(zones, [[]])

        self.assertEqual(
            huawei._list_zone_ids(client, FAKE_SDK),
            [
                "cn-north-4-incomplete",
                "cn-north-4-legacy",
                "cn-north-4-no-mode",
                "cn-north-4-no-type",
                "cn-north-4a",
            ],
        )

    def test_region_projects_only_uses_enabled_public_region_projects(self):
        regions = [
            {"id": "cn-north-4", "type": "public"},
            {"id": "cn-east-3", "type": "public"},
            {"id": "private-1", "type": "private"},
            {"id": "invalid/endpoint", "type": "public"},
        ]
        projects = [
            {"id": "p-north", "name": "cn-north-4", "enabled": True},
            {"id": "p-east", "name": "cn-east-3", "enabled": False},
            {"id": "p-private", "name": "private-1", "enabled": True},
            {"id": "p-child", "name": "application", "enabled": True},
        ]

        self.assertEqual(
            huawei._region_projects(regions, projects),
            [("cn-north-4", "p-north")],
        )

    def test_availability_uses_region_default_and_az_overrides(self):
        extra = {
            "cond:operation:status": "abandon",
            "cond:operation:az": (
                "cn-north-4a(normal), cn-north-4b(sellout), "
                "cn-north-4c(promotion)"
            ),
            "cond:operation:charge": "period,demand",
        }

        available, zones = huawei._available_zones(
            extra,
            ["cn-north-4a", "cn-north-4b", "cn-north-4c", "cn-north-4d"],
        )

        self.assertTrue(available)
        self.assertEqual(zones, ["cn-north-4a", "cn-north-4c"])
        self.assertTrue(huawei._normal_charge_supported(extra))
        self.assertFalse(
            huawei._normal_charge_supported(
                {"cond:operation:charge": "spot"}
            )
        )

    def test_record_maps_specs_and_preserves_types_without_current_stock(self):
        record = huawei._record_for_flavor(
            flavor(
                "pi2.2xlarge.4",
                vcpus="8",
                ram=32768,
                extra={
                    "ecs:performancetype": "gpu",
                    "cond:operation:status": "normal",
                    "ecs:instance_architecture": "arm64",
                    "info:cpu:name": "Huawei Kunpeng",
                    "quota:gpu": "NVIDIA V100",
                    "info:gpus": '[{"name":"Ascend","count":2}]',
                    "quota:max_rate": "10000",
                    "quota:min_rate": "2000",
                    "quota:max_pps": "1200000",
                    "quota:nvme_ssd": "3.2T:large:3200:true",
                },
            ),
            "cn-north-4",
            ["cn-north-4a"],
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["family"], "pi2")
        self.assertEqual(record["memoryGiB"], 32)
        self.assertEqual(record["architecture"], "arm64")
        self.assertEqual(record["gpuCount"], 2)
        self.assertEqual(
            record["networkPerformance"],
            "10 Gbps max / 2 Gbps assured; 1,200,000 PPS",
        )
        self.assertEqual(record["localStorage"], "Local NVMe SSD")

        sold_out = flavor(
            "c7.large.2",
            extra={"cond:operation:status": "sellout"},
        )
        sold_out_record = huawei._record_for_flavor(
            sold_out,
            "cn-north-4",
            ["cn-north-4a"],
        )
        self.assertIsNotNone(sold_out_record)
        assert sold_out_record is not None
        self.assertEqual(sold_out_record["regions"], [])
        self.assertEqual(sold_out_record["zones"], [])

        spot_only_record = huawei._record_for_flavor(
            flavor(
                "gpu.spot-only",
                extra={
                    "cond:operation:status": "normal",
                    "cond:operation:charge": "spot",
                },
            ),
            "cn-north-4",
            ["cn-north-4a"],
        )
        self.assertIsNotNone(spot_only_record)
        assert spot_only_record is not None
        self.assertEqual(spot_only_record["regions"], [])
        self.assertEqual(spot_only_record["zones"], [])
        self.assertIsNone(
            huawei._record_for_flavor(
                flavor("private.large", public=False),
                "cn-north-4",
                ["cn-north-4a"],
            )
        )
        self.assertIsNone(
            huawei._record_for_flavor(
                flavor("disabled.large", disabled=True),
                "cn-north-4",
                ["cn-north-4a"],
            )
        )

    def test_fetch_paginates_and_merges_the_same_flavor_across_regions(self):
        regions = [
            SimpleNamespace(id="cn-east-3", type="public"),
            SimpleNamespace(id="cn-north-4", type="public"),
        ]
        projects = [
            SimpleNamespace(id="p-east", name="cn-east-3", enabled=True),
            SimpleNamespace(id="p-north", name="cn-north-4", enabled=True),
        ]
        shared_east = flavor(
            "c7.large.2",
            extra={
                "ecs:performancetype": "computingv3",
                "cond:operation:status": "normal",
                "info:cpu:name": "Intel Xeon",
            },
        )
        shared_north = flavor(
            "c7.large.2",
            extra={
                "ecs:performancetype": "computingv3",
                "cond:operation:status": "abandon",
                "cond:operation:az": "cn-north-4a(normal),cn-north-4b(sellout)",
                "info:cpu:name": "Intel Xeon",
            },
        )
        memory = flavor(
            "m7.xlarge.8",
            extra={
                "ecs:performancetype": "highmem",
                "cond:operation:status": "normal",
            },
        )
        sold_out = flavor(
            "s7.large.4",
            extra={"cond:operation:status": "sellout"},
        )
        clients = {
            "cn-east-3": FakeEcsClient(
                ["cn-east-3a"],
                [[shared_east, sold_out], []],
            ),
            "cn-north-4": FakeEcsClient(
                ["cn-north-4a", "cn-north-4b"],
                [[shared_north, memory], []],
            ),
        }

        with (
            patch.object(
                huawei,
                "require_env",
                return_value=("access-key", "secret-key"),
            ) as require_env,
            patch.object(huawei, "_load_sdk", return_value=FAKE_SDK),
            patch.object(
                huawei,
                "_build_iam_client",
                return_value=FakeIamClient(regions, projects),
            ),
            patch.object(
                huawei,
                "_build_ecs_client",
                side_effect=lambda _ak, _sk, _project, region, _sdk: clients[
                    region
                ],
            ),
            patch.object(huawei, "PAGE_SIZE", 2),
        ):
            result = huawei.fetch()

        require_env.assert_called_once_with(
            "HUAWEI_ACCESS_KEY_ID",
            "HUAWEI_SECRET_ACCESS_KEY",
        )
        self.assertEqual(result["slug"], "huawei")
        self.assertEqual(result["regionCount"], 2)
        self.assertEqual(result["zoneCount"], 3)
        self.assertEqual(result["skippedRegions"], [])
        self.assertEqual(len(result["instances"]), 3)
        by_type = {item["instanceType"]: item for item in result["instances"]}
        self.assertEqual(
            by_type["c7.large.2"]["regions"],
            ["cn-east-3", "cn-north-4"],
        )
        self.assertEqual(
            by_type["c7.large.2"]["zones"],
            ["cn-east-3a", "cn-north-4a"],
        )
        self.assertEqual(by_type["c7.large.2"]["category"], "Compute optimized")
        self.assertEqual(by_type["m7.xlarge.8"]["category"], "Memory optimized")
        self.assertEqual(by_type["s7.large.4"]["regions"], [])
        self.assertEqual(by_type["s7.large.4"]["zones"], [])
        self.assertEqual(clients["cn-east-3"].markers, [None, "s7.large.4"])
        self.assertEqual(clients["cn-north-4"].markers, [None, "m7.xlarge.8"])

    def test_fetch_skips_only_forbidden_region_and_reports_it(self):
        regions = [
            SimpleNamespace(id="cn-east-3", type="public"),
            SimpleNamespace(id="cn-north-4", type="public"),
        ]
        projects = [
            SimpleNamespace(id="p-east", name="cn-east-3", enabled=True),
            SimpleNamespace(id="p-north", name="cn-north-4", enabled=True),
        ]
        clients = {
            "cn-east-3": FakeEcsClient(
                [],
                [],
                zone_error=FakeClientRequestException("APIGW.0802"),
            ),
            "cn-north-4": FakeEcsClient(
                ["cn-north-4a"],
                [[flavor("c7.large.2")]],
            ),
        }

        with (
            patch.object(
                huawei,
                "require_env",
                return_value=("access-key", "secret-key"),
            ),
            patch.object(huawei, "_load_sdk", return_value=FAKE_SDK),
            patch.object(
                huawei,
                "_build_iam_client",
                return_value=FakeIamClient(regions, projects),
            ),
            patch.object(
                huawei,
                "_build_ecs_client",
                side_effect=lambda _ak, _sk, _project, region, _sdk: clients[
                    region
                ],
            ),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                result = huawei.fetch()

        self.assertEqual(result["regionCount"], 1)
        self.assertEqual(result["zoneCount"], 1)
        self.assertEqual(result["skippedRegions"], ["cn-east-3"])
        self.assertEqual(len(result["instances"]), 1)
        self.assertEqual(result["instances"][0]["regions"], ["cn-north-4"])
        self.assertIn("::warning", output.getvalue())
        self.assertIn("cn-east-3", output.getvalue())
        self.assertIn("APIGW.0802", output.getvalue())

    def test_fetch_propagates_other_forbidden_errors(self):
        regions = [SimpleNamespace(id="cn-east-3", type="public")]
        projects = [
            SimpleNamespace(id="p-east", name="cn-east-3", enabled=True)
        ]
        error = FakeClientRequestException("APIGW.0803")

        with (
            patch.object(
                huawei,
                "require_env",
                return_value=("access-key", "secret-key"),
            ),
            patch.object(huawei, "_load_sdk", return_value=FAKE_SDK),
            patch.object(
                huawei,
                "_build_iam_client",
                return_value=FakeIamClient(regions, projects),
            ),
            patch.object(
                huawei,
                "_build_ecs_client",
                return_value=FakeEcsClient([], [], zone_error=error),
            ),
        ):
            with self.assertRaises(FakeClientRequestException) as raised:
                huawei.fetch()

        self.assertIs(raised.exception, error)


if __name__ == "__main__":
    unittest.main()
