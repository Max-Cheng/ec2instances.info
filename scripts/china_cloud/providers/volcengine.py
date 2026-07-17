from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from scripts.china_cloud.common import (
    family_from_instance_type,
    integer,
    normalize_architecture,
    number,
    provider_result,
    require_env,
)


BOOTSTRAP_REGION = "cn-beijing"
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 20
SOURCE_URL = (
    "https://api.volcengine.com/api-docs/view?"
    "action=DescribeInstanceTypes&serviceCode=ecs&version=2020-04-01"
)


def _sdk() -> tuple[Any, Any]:
    try:
        import volcenginesdkcore
        import volcenginesdkecs
    except ImportError as error:  # pragma: no cover - exercised by the workflow environment
        raise RuntimeError(
            "volcengine-python-sdk is required; install scripts/china_cloud/requirements.txt"
        ) from error
    return volcenginesdkcore, volcenginesdkecs


def _client(
    core: Any,
    ecs: Any,
    access_key: str,
    secret_key: str,
    region: str,
) -> Any:
    configuration = core.Configuration()
    configuration.ak = access_key
    configuration.sk = secret_key
    configuration.region = region
    configuration.debug = False
    configuration.connect_timeout = CONNECT_TIMEOUT_SECONDS
    configuration.read_timeout = READ_TIMEOUT_SECONDS
    configuration.auto_retry = False
    return ecs.ECSApi(core.ApiClient(configuration))


def _value(value: Any, *names: str, default: Any = None) -> Any:
    if value is None:
        return default
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _list(value: Any, *names: str) -> list[Any]:
    items = _value(value, *names, default=[])
    return list(items or [])


def _paginated_regions(client: Any, ecs: Any) -> list[str]:
    regions: set[str] = set()
    next_token: str | None = None
    seen_tokens: set[str] = set()

    while True:
        request = ecs.DescribeRegionsRequest(max_results=20, next_token=next_token)
        response = client.describe_regions(request)
        for region in _list(response, "regions", "Regions"):
            region_id = str(_value(region, "region_id", "RegionId", default="")).strip()
            if region_id:
                regions.add(region_id)

        token = str(_value(response, "next_token", "NextToken", default="") or "")
        if not token:
            break
        if token in seen_tokens:
            raise RuntimeError("DescribeRegions returned a repeated NextToken")
        seen_tokens.add(token)
        next_token = token

    return sorted(regions)


def _paginated_instance_types(client: Any, ecs: Any) -> list[Any]:
    instance_types: list[Any] = []
    next_token: str | None = None
    seen_tokens: set[str] = set()

    while True:
        request = ecs.DescribeInstanceTypesRequest(
            max_results=1000,
            next_token=next_token,
        )
        response = client.describe_instance_types(request)
        instance_types.extend(_list(response, "instance_types", "InstanceTypes"))

        token = str(_value(response, "next_token", "NextToken", default="") or "")
        if not token:
            break
        if token in seen_tokens:
            raise RuntimeError("DescribeInstanceTypes returned a repeated NextToken")
        seen_tokens.add(token)
        next_token = token

    return instance_types


def _zones(client: Any, ecs: Any) -> list[str]:
    response = client.describe_zones(ecs.DescribeZonesRequest())
    return sorted(
        {
            str(_value(zone, "zone_id", "ZoneId", default="")).strip()
            for zone in _list(response, "zones", "Zones")
            if str(_value(zone, "zone_id", "ZoneId", default="")).strip()
        }
    )


def _available_instance_types(
    client: Any,
    ecs: Any,
    region: str,
) -> tuple[dict[str, dict[str, set[str]]], set[str]]:
    request = ecs.DescribeAvailableResourceRequest(
        destination_resource="InstanceType",
        instance_charge_type="PostPaid",
        spot_strategy="NoSpot",
    )
    response = client.describe_available_resource(request)
    available: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"regions": set(), "zones": set()}
    )
    discovered_zones: set[str] = set()

    for available_zone in _list(response, "available_zones", "AvailableZones"):
        zone_status = str(
            _value(available_zone, "status", "Status", default="") or ""
        ).strip().lower()
        if zone_status and zone_status != "available":
            continue
        zone_id = str(
            _value(available_zone, "zone_id", "ZoneId", default="")
        ).strip()
        response_region = str(
            _value(available_zone, "region_id", "RegionId", default=region)
        ).strip()
        if zone_id:
            discovered_zones.add(zone_id)

        for resource in _list(
            available_zone,
            "available_resources",
            "AvailableResources",
        ):
            resource_type = str(_value(resource, "type", "Type", default=""))
            if resource_type.lower() != "instancetype":
                continue
            for supported in _list(
                resource,
                "supported_resources",
                "SupportedResources",
            ):
                status = str(
                    _value(supported, "status", "Status", default="")
                ).lower()
                instance_type = str(
                    _value(supported, "value", "Value", default="")
                ).strip()
                if status == "available" and instance_type:
                    available[instance_type]["regions"].add(
                        response_region or region
                    )
                    if zone_id:
                        available[instance_type]["zones"].add(zone_id)

    return available, discovered_zones


def _family(instance_type: str, raw_family: Any) -> str:
    family = str(raw_family or "").strip()
    if family.startswith("ecs."):
        family = family[4:]
    return family or family_from_instance_type(instance_type)


def _architecture(processor_model: str, instance_type: str) -> str:
    text = f"{processor_model} {instance_type}".lower()
    if any(token in text for token in ("ampere", "neoverse", "aarch64", "arm")):
        return "arm64"
    return normalize_architecture(processor_model, instance_type)


def _bandwidth(value: Any) -> str:
    mbps = number(value)
    if mbps <= 0:
        return ""
    if mbps >= 1000:
        return f"{mbps / 1000:g} Gbps"
    return f"{mbps:g} Mbps"


def _network_performance(network: Any) -> str:
    baseline = _bandwidth(
        _value(network, "baseline_bandwidth_mbps", "BaselineBandwidthMbps")
    )
    maximum = _bandwidth(
        _value(network, "maximum_bandwidth_mbps", "MaximumBandwidthMbps")
    )
    throughput = number(
        _value(network, "maximum_throughput_kpps", "MaximumThroughputKpps")
    )

    parts: list[str] = []
    if baseline and maximum and baseline != maximum:
        parts.append(f"{baseline} baseline / {maximum} maximum")
    elif maximum or baseline:
        parts.append(maximum or baseline)
    if throughput > 0:
        parts.append(f"{throughput:g} Kpps")
    return "; ".join(parts) or "Not published"


def _local_storage(local_volumes: list[Any]) -> str:
    volumes: list[str] = []
    for volume in local_volumes:
        count = integer(_value(volume, "count", "Count"))
        size = number(_value(volume, "size", "Size"))
        volume_type = str(
            _value(volume, "volume_type", "VolumeType", default="local disk")
            or "local disk"
        ).strip()
        if count <= 0:
            continue
        size_text = f" {size:g} GiB" if size > 0 else ""
        volumes.append(f"{count} x{size_text} {volume_type}")
    return "; ".join(volumes) or "Cloud disks"


def _gpu(specification: Any) -> tuple[int, str]:
    gpu = _value(specification, "gpu", "Gpu")
    devices = _list(gpu, "gpu_devices", "GpuDevices")
    count = sum(integer(_value(device, "count", "Count")) for device in devices)
    products = sorted(
        {
            str(_value(device, "product_name", "ProductName", default="")).strip()
            for device in devices
            if str(
                _value(device, "product_name", "ProductName", default="")
            ).strip()
        }
    )
    return count, " ".join(products)


def _record(
    specification: Any,
    available_regions: set[str],
    available_zones: set[str],
) -> dict[str, Any]:
    instance_type = str(
        _value(specification, "instance_type_id", "InstanceTypeId", default="")
    ).strip()
    family = _family(
        instance_type,
        _value(specification, "instance_type_family", "InstanceTypeFamily"),
    )
    processor = _value(specification, "processor", "Processor")
    memory = _value(specification, "memory", "Memory")
    processor_model = str(
        _value(processor, "model", "Model", default="Provider-managed CPU")
        or "Provider-managed CPU"
    ).strip()
    gpu_count, gpu_hint = _gpu(specification)
    category_hint = " ".join(
        part
        for part in (
            gpu_hint,
            "GPU accelerated" if gpu_count else "",
        )
        if part
    )

    record: dict[str, Any] = {
        "instanceType": instance_type,
        "family": family,
        "familyName": family,
        "vCPU": integer(_value(processor, "cpus", "Cpus")),
        "memoryGiB": number(_value(memory, "size", "Size")) / 1024,
        "architecture": _architecture(processor_model, instance_type),
        "processor": processor_model,
        "networkPerformance": _network_performance(
            _value(specification, "network", "Network")
        ),
        "localStorage": _local_storage(
            _list(specification, "local_volumes", "LocalVolumes")
        ),
        "sourceUrl": SOURCE_URL,
        "regions": sorted(available_regions),
        "zones": sorted(available_zones),
    }
    if gpu_count > 0:
        record["gpuCount"] = gpu_count
    if category_hint:
        record["categoryHint"] = category_hint
    return record


def fetch() -> dict[str, Any]:
    access_key, secret_key = require_env(
        "VOLCENGINE_ACCESS_KEY_ID",
        "VOLCENGINE_SECRET_ACCESS_KEY",
    )
    core, ecs = _sdk()
    bootstrap_client = _client(
        core,
        ecs,
        access_key,
        secret_key,
        BOOTSTRAP_REGION,
    )

    regions = _paginated_regions(bootstrap_client, ecs)
    specifications = _paginated_instance_types(bootstrap_client, ecs)
    all_zones: set[str] = set()
    availability: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"regions": set(), "zones": set()}
    )

    for region in regions:
        client = (
            bootstrap_client
            if region == BOOTSTRAP_REGION
            else _client(core, ecs, access_key, secret_key, region)
        )
        region_zones = set(_zones(client, ecs))
        available, discovered_zones = _available_instance_types(client, ecs, region)
        all_zones.update(region_zones)
        all_zones.update(discovered_zones)

        for instance_type, locations in available.items():
            availability[instance_type]["regions"].update(locations["regions"])
            availability[instance_type]["zones"].update(locations["zones"])

    records = [
        _record(
            specification,
            availability[instance_type]["regions"],
            availability[instance_type]["zones"],
        )
        for specification in specifications
        if (
            instance_type := str(
                _value(
                    specification,
                    "instance_type_id",
                    "InstanceTypeId",
                    default="",
                )
            ).strip()
        )
    ]
    return provider_result("volcengine", records, regions, all_zones)
