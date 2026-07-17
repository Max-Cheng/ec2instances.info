from __future__ import annotations

import importlib
import json
from collections import defaultdict
from typing import Any

from scripts.china_cloud.common import integer, nonempty, number, provider_result, require_env


SOURCE_URL = (
    "https://help.aliyun.com/en/ecs/developer-reference/"
    "api-ecs-2014-05-26-describeinstancetypes"
)
BOOTSTRAP_REGION = "cn-hangzhou"


def _make_client(access_key_id: str, access_key_secret: str, region_id: str) -> Any:
    from aliyunsdkcore.client import AcsClient

    return AcsClient(
        access_key_id,
        access_key_secret,
        region_id,
        auto_retry=True,
        max_retry_time=3,
        port=443,
        connect_timeout=10,
        timeout=60,
        debug=False,
    )


def _invoke(client: Any, action: str, **parameters: Any) -> dict[str, Any]:
    module = importlib.import_module(
        f"aliyunsdkecs.request.v20140526.{action}Request"
    )
    request_class = getattr(module, f"{action}Request")
    request = request_class()
    request.set_protocol_type("https")
    request.set_accept_format("json")
    for name, value in parameters.items():
        if value is None:
            continue
        setter = getattr(request, f"set_{name}", None)
        if setter is not None:
            setter(value)
        else:
            request.add_query_param(name, value)

    payload = client.do_action_with_exception(request)
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Alibaba Cloud {action} returned a non-object response")
    return payload


def _nested_list(payload: dict[str, Any], *path: str) -> list[dict[str, Any]]:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return []
        value = value.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _has_stock(item: dict[str, Any]) -> bool:
    status = str(item.get("Status") or "").strip().lower()
    if status and status != "available":
        return False
    category = str(item.get("StatusCategory") or "").replace("_", "").lower()
    return category not in {"withoutstock", "closedwithoutstock"}


def _compact(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _network_performance(spec: dict[str, Any]) -> str:
    bandwidth = max(
        number(spec.get("InstanceBandwidthRx")),
        number(spec.get("InstanceBandwidthTx")),
    )
    packets = max(
        number(spec.get("InstancePpsRx")),
        number(spec.get("InstancePpsTx")),
    )
    details: list[str] = []
    if bandwidth > 0:
        details.append(f"Up to {_compact(bandwidth / 1_000_000)} Gbps")
    if packets > 0:
        details.append(f"{_compact(packets / 1_000_000)} Mpps")
    return "; ".join(details) or "Not published"


def _local_storage(spec: dict[str, Any]) -> str:
    amount = integer(spec.get("LocalStorageAmount"))
    capacity = number(spec.get("LocalStorageCapacity"))
    category = str(spec.get("LocalStorageCategory") or "").strip()
    if amount <= 0 or capacity <= 0:
        return "Cloud disks"
    suffix = f" {category}" if category else " local storage"
    return f"{amount} x {_compact(capacity)} GiB{suffix}"


def _family(spec: dict[str, Any], instance_type: str) -> str:
    family = str(spec.get("InstanceTypeFamily") or "").strip()
    if family.startswith("ecs."):
        family = family[4:]
    if family:
        return family
    parts = instance_type.split(".")
    return parts[1] if instance_type.startswith("ecs.") and len(parts) > 2 else instance_type


def _fetch_instance_types(client: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    next_token = ""
    seen_tokens: set[str] = set()
    while True:
        parameters: dict[str, Any] = {"MaxResults": 100}
        if next_token:
            parameters["NextToken"] = next_token
        payload = _invoke(client, "DescribeInstanceTypes", **parameters)
        records.extend(_nested_list(payload, "InstanceTypes", "InstanceType"))

        new_token = str(payload.get("NextToken") or "").strip()
        if not new_token:
            return records
        if new_token in seen_tokens:
            raise RuntimeError("Alibaba Cloud DescribeInstanceTypes repeated NextToken")
        seen_tokens.add(new_token)
        next_token = new_token


def _availability(
    access_key_id: str,
    access_key_secret: str,
    region_ids: list[str],
) -> tuple[dict[str, dict[str, set[str]]], set[str]]:
    available: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"regions": set(), "zones": set()}
    )
    all_zones: set[str] = set()

    for region_id in region_ids:
        client = _make_client(access_key_id, access_key_secret, region_id)
        zone_payload = _invoke(
            client,
            "DescribeZones",
            InstanceChargeType="PostPaid",
            SpotStrategy="NoSpot",
            AcceptLanguage="en-US",
        )
        all_zones.update(
            zone_id
            for item in _nested_list(zone_payload, "Zones", "Zone")
            if (zone_id := str(item.get("ZoneId") or "").strip())
        )

        resource_payload = _invoke(
            client,
            "DescribeAvailableResource",
            DestinationResource="InstanceType",
            ResourceType="instance",
            InstanceChargeType="PostPaid",
        )
        for zone in _nested_list(resource_payload, "AvailableZones", "AvailableZone"):
            if not _has_stock(zone):
                continue
            zone_id = str(zone.get("ZoneId") or "").strip()
            for resource in _nested_list(
                zone, "AvailableResources", "AvailableResource"
            ):
                resource_type = str(resource.get("Type") or "").lower()
                if resource_type and resource_type != "instancetype":
                    continue
                for supported in _nested_list(
                    resource, "SupportedResources", "SupportedResource"
                ):
                    if not _has_stock(supported):
                        continue
                    instance_type = str(supported.get("Value") or "").strip()
                    if not instance_type:
                        continue
                    available[instance_type]["regions"].add(region_id)
                    if zone_id:
                        available[instance_type]["zones"].add(zone_id)

    return available, all_zones


def fetch() -> dict[str, Any]:
    access_key_id, access_key_secret = require_env(
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    )
    bootstrap_client = _make_client(
        access_key_id, access_key_secret, BOOTSTRAP_REGION
    )
    region_payload = _invoke(
        bootstrap_client, "DescribeRegions", AcceptLanguage="en-US"
    )
    region_ids = sorted(
        {
            region_id
            for item in _nested_list(region_payload, "Regions", "Region")
            if (region_id := str(item.get("RegionId") or "").strip())
        }
    )

    specs = _fetch_instance_types(bootstrap_client)
    available, zones = _availability(
        access_key_id, access_key_secret, region_ids
    )

    records: list[dict[str, Any]] = []
    for spec in specs:
        instance_type = str(spec.get("InstanceTypeId") or "").strip()
        if not instance_type:
            continue
        family = _family(spec, instance_type)
        inventory = available.get(instance_type, {"regions": set(), "zones": set()})
        records.append(
            {
                "instanceType": instance_type,
                "family": family,
                "familyName": nonempty(spec.get("InstanceTypeFamily"), family),
                "vCPU": number(spec.get("CpuCoreCount")),
                "memoryGiB": number(spec.get("MemorySize")),
                "architecture": spec.get("CpuArchitecture"),
                "processor": nonempty(
                    spec.get("PhysicalProcessorModel"), "Provider-managed CPU"
                ),
                "networkPerformance": _network_performance(spec),
                "localStorage": _local_storage(spec),
                "sourceUrl": SOURCE_URL,
                "regions": sorted(inventory["regions"]),
                "zones": sorted(inventory["zones"]),
                "gpuCount": number(spec.get("GPUAmount")),
                "categoryHint": " ".join(
                    str(value)
                    for value in (
                        spec.get("InstanceCategory"),
                        spec.get("InstanceTypeFamily"),
                        spec.get("GPUSpec"),
                    )
                    if value
                ),
            }
        )

    return provider_result("alibaba", records, region_ids, zones)
