from __future__ import annotations

import importlib
import json
from collections import defaultdict
from typing import Any

from scripts.china_cloud.common import integer, nonempty, number, provider_result, require_env


SOURCE_URL = "https://cloud.tencent.com/document/product/213/15749"


def _client_profile(endpoint: str) -> Any:
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile

    http_profile = HttpProfile(
        protocol="https",
        endpoint=endpoint,
        reqMethod="POST",
        reqTimeout=60,
    )
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    return client_profile


def _make_region_client(secret_id: str, secret_key: str) -> Any:
    from tencentcloud.common import credential
    from tencentcloud.region.v20220627.region_client import RegionClient

    return RegionClient(
        credential.Credential(secret_id, secret_key),
        "",
        _client_profile("region.tencentcloudapi.com"),
    )


def _make_cvm_client(secret_id: str, secret_key: str, region: str) -> Any:
    from tencentcloud.common import credential
    from tencentcloud.cvm.v20170312.cvm_client import CvmClient

    return CvmClient(
        credential.Credential(secret_id, secret_key),
        region,
        _client_profile("cvm.tencentcloudapi.com"),
    )


def _call(
    client: Any,
    models_module: str,
    request_class: str,
    method: str,
    **parameters: Any,
) -> dict[str, Any]:
    models = importlib.import_module(models_module)
    request = getattr(models, request_class)()
    request.from_json_string(json.dumps(parameters))
    response = getattr(client, method)(request)
    if isinstance(response, dict):
        return response
    if isinstance(response, bytes):
        response = response.decode("utf-8")
    if isinstance(response, str):
        result = json.loads(response)
    elif hasattr(response, "to_json_string"):
        result = json.loads(response.to_json_string())
    else:
        raise RuntimeError(f"Tencent Cloud {method} returned an unsupported response")
    if not isinstance(result, dict):
        raise RuntimeError(f"Tencent Cloud {method} returned a non-object response")
    return result


def _items(payload: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = payload.get(name)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _available_or_unspecified(item: dict[str, Any], state_field: str) -> bool:
    state = str(item.get(state_field) or "").strip().upper()
    return not state or state == "AVAILABLE"


def _compact(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _network_performance(item: dict[str, Any]) -> str:
    bandwidth = number(item.get("InstanceBandwidth"))
    packets = number(item.get("InstancePps"))
    details: list[str] = []
    if bandwidth > 0:
        details.append(f"Up to {_compact(bandwidth)} Gbps")
    if packets > 0:
        details.append(f"{_compact(packets)} x 10k PPS")
    return "; ".join(details) or "Not published"


def _local_storage(item: dict[str, Any]) -> str:
    disks = item.get("LocalDiskTypeList")
    labels: list[str] = []
    if isinstance(disks, list):
        for disk in disks:
            if not isinstance(disk, dict):
                continue
            disk_type = str(disk.get("Type") or "local disk").strip()
            minimum = number(disk.get("MinSize"))
            maximum = number(disk.get("MaxSize"))
            if minimum > 0 and maximum > 0 and minimum != maximum:
                labels.append(
                    f"{disk_type} {_compact(minimum)}-{_compact(maximum)} GiB"
                )
            elif maximum > 0 or minimum > 0:
                labels.append(f"{disk_type} {_compact(maximum or minimum)} GiB")
            else:
                labels.append(disk_type)
    if labels:
        amount = integer(item.get("StorageBlockAmount"))
        prefix = f"{amount} x " if amount > 0 and len(labels) == 1 else ""
        return prefix + ", ".join(labels)
    return "Cloud Block Storage"


def _processor(item: dict[str, Any]) -> str:
    processor = str(item.get("CpuType") or "").strip()
    frequency = number(item.get("Frequency"))
    if processor and frequency > 0:
        return f"{processor} @ {_compact(frequency)} GHz"
    return processor or "Provider-managed CPU"


def _is_sellable(item: dict[str, Any]) -> bool:
    if str(item.get("Status") or "").strip().upper() != "SELL":
        return False
    status_category = str(item.get("StatusCategory") or "").replace("_", "").lower()
    return status_category != "withoutstock"


def _merged_record(
    spec: dict[str, Any],
    quota: dict[str, Any],
    region: str,
) -> dict[str, Any] | None:
    item = dict(spec)
    for key, value in quota.items():
        if value is not None and value != "":
            item[key] = value

    instance_type = str(item.get("InstanceType") or "").strip()
    if not instance_type:
        return None
    family = str(item.get("InstanceFamily") or "").strip() or instance_type.split(".", 1)[0]
    zone = str(item.get("Zone") or "").strip()
    sellable = bool(quota) and _is_sellable(quota)
    return {
        "instanceType": instance_type,
        "family": family,
        "familyName": nonempty(item.get("TypeName"), family),
        "vCPU": number(item.get("Cpu") if item.get("Cpu") is not None else item.get("CPU")),
        "memoryGiB": number(item.get("Memory")),
        "architecture": item.get("CpuType"),
        "processor": _processor(item),
        "networkPerformance": _network_performance(item),
        "localStorage": _local_storage(item),
        "sourceUrl": SOURCE_URL,
        "regions": [region] if sellable else [],
        "zones": [zone] if sellable and zone else [],
        "gpuCount": number(
            item.get("GpuCount")
            if item.get("GpuCount") is not None
            else item.get("Gpu") or item.get("GPU")
        ),
        "categoryHint": " ".join(
            str(value)
            for value in (
                item.get("TypeName"),
                item.get("Remark"),
                item.get("InstanceFamily"),
                item.get("Gpu"),
                item.get("GPU"),
                item.get("Fpga"),
                item.get("FPGA"),
            )
            if value
        ),
    }


def fetch() -> dict[str, Any]:
    secret_id, secret_key = require_env(
        "TENCENTCLOUD_SECRET_ID",
        "TENCENTCLOUD_SECRET_KEY",
    )
    region_payload = _call(
        _make_region_client(secret_id, secret_key),
        "tencentcloud.region.v20220627.models",
        "DescribeRegionsRequest",
        "DescribeRegions",
        Product="cvm",
        Scene=1,
    )
    regions = sorted(
        {
            region
            for item in _items(region_payload, "RegionSet")
            if _available_or_unspecified(item, "RegionState")
            if (region := str(item.get("Region") or "").strip())
        }
    )

    all_zones: set[str] = set()
    records: list[dict[str, Any]] = []
    for region in regions:
        client = _make_cvm_client(secret_id, secret_key, region)
        zone_payload = _call(
            client,
            "tencentcloud.cvm.v20170312.models",
            "DescribeZonesRequest",
            "DescribeZones",
        )
        all_zones.update(
            zone
            for item in _items(zone_payload, "ZoneSet")
            if _available_or_unspecified(item, "ZoneState")
            if (zone := str(item.get("Zone") or "").strip())
        )

        spec_payload = _call(
            client,
            "tencentcloud.cvm.v20170312.models",
            "DescribeInstanceTypeConfigsRequest",
            "DescribeInstanceTypeConfigs",
        )
        quota_payload = _call(
            client,
            "tencentcloud.cvm.v20170312.models",
            "DescribeZoneInstanceConfigInfosRequest",
            "DescribeZoneInstanceConfigInfos",
            Filters=[
                {
                    "Name": "instance-charge-type",
                    "Values": ["POSTPAID_BY_HOUR"],
                }
            ],
        )
        specs = _items(spec_payload, "InstanceTypeConfigSet")
        quotas = _items(quota_payload, "InstanceTypeQuotaSet")

        quota_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        quota_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for quota in quotas:
            instance_type = str(quota.get("InstanceType") or "").strip()
            zone = str(quota.get("Zone") or "").strip()
            if not instance_type:
                continue
            quota_by_key[(instance_type, zone)] = quota
            quota_by_type[instance_type].append(quota)

        emitted_keys: set[tuple[str, str]] = set()
        for spec in specs:
            instance_type = str(spec.get("InstanceType") or "").strip()
            zone = str(spec.get("Zone") or "").strip()
            if not instance_type:
                continue
            matching = quota_by_key.get((instance_type, zone))
            if matching is None and not zone and len(quota_by_type[instance_type]) == 1:
                matching = quota_by_type[instance_type][0]
            record = _merged_record(spec, matching or {}, region)
            if record is not None:
                records.append(record)
            if matching is not None:
                emitted_keys.add(
                    (
                        instance_type,
                        str(matching.get("Zone") or "").strip(),
                    )
                )

        for key, quota in quota_by_key.items():
            if key in emitted_keys:
                continue
            record = _merged_record({}, quota, region)
            if record is not None:
                records.append(record)

    return provider_result("tencent", records, regions, all_zones)
