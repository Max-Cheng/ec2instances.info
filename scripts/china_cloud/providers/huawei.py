from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from scripts.china_cloud.common import (
    family_from_instance_type,
    format_packet_rate,
    number,
    provider_result,
    require_env,
)


PAGE_SIZE = 1000
IAM_REGION = "cn-north-4"
IAM_ENDPOINT = "https://iam.cn-north-4.myhuaweicloud.com"
SOURCE_URL = (
    "https://support.huaweicloud.com/api-ecs/zh-cn_topic_0020212656.html"
)

# `obt` is an orderable public-beta state. The sold-out and withdrawn variants
# are deliberately absent from this set.
AVAILABLE_STATES = {"normal", "promotion", "obt"}
NORMAL_CHARGE_MODES = {"demand", "period"}
HTTP_TIMEOUT_SECONDS = (5, 20)

PERFORMANCE_NAMES = {
    "normal": "General-purpose",
    "entry": "Entry-level general-purpose",
    "computingv3": "General computing-plus",
    "cpuv1": "Compute I",
    "cpuv2": "Compute II",
    "highcpu": "High-performance compute",
    "ultracpu": "Ultra-high-performance compute",
    "highmem": "Memory-optimized",
    "saphana": "Large-memory",
    "diskintensive": "Disk-intensive",
    "highio": "Ultra-high I/O",
    "gpu": "GPU-accelerated",
    "fpga": "FPGA-accelerated",
    "ascend": "AI-accelerated",
    "kunpeng_computing": "Kunpeng general computing-plus",
    "kunpeng_highmem": "Kunpeng memory-optimized",
    "kunpeng_highio": "Kunpeng ultra-high I/O",
    "kunpeng_accelerator": "Kunpeng accelerated",
    "advanced_smb": "General computing",
}

EXTRA_ATTRIBUTES = {
    "ecs:performancetype": "ecsperformancetype",
    "hws:performancetype": "hwsperformancetype",
    "cond:operation:status": "condoperationstatus",
    "cond:operation:az": "condoperationaz",
    "cond:operation:charge": "condoperationcharge",
    "ecs:instance_architecture": "ecsinstance_architecture",
    "info:cpu:name": "infocpuname",
    "info:gpus": "infogpus",
    "quota:gpu": "quotagpu",
    "pci_passthrough:alias": "pci_passthroughalias",
    "pci_passthrough:gpu_specs": "pci_passthroughgpu_specs",
    "quota:max_rate": "quotamax_rate",
    "quota:min_rate": "quotamin_rate",
    "quota:max_pps": "quotamax_pps",
    "instance_vnic:instance_bandwidth": "instance_vnicinstance_bandwidth",
    "quota:local_disk": "quotalocal_disk",
    "quota:nvme_ssd": "quotanvme_ssd",
}


@dataclass(frozen=True)
class _HuaweiSdk:
    GlobalCredentials: Any
    BasicCredentials: Any
    Region: Any
    IamClient: Any
    EcsClient: Any
    KeystoneListRegionsRequest: Any
    KeystoneListAuthProjectsRequest: Any
    ListFlavorsRequest: Any
    ListServerAzInfoRequest: Any


def _load_sdk() -> _HuaweiSdk:
    """Import SDKs lazily so offline unit tests do not require vendor wheels."""

    try:
        from huaweicloudsdkcore.auth.credentials import (
            BasicCredentials,
            GlobalCredentials,
        )
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkecs.v2 import (
            EcsClient,
            ListFlavorsRequest,
            ListServerAzInfoRequest,
        )
        from huaweicloudsdkiam.v3 import (
            IamClient,
            KeystoneListAuthProjectsRequest,
            KeystoneListRegionsRequest,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime
        raise RuntimeError(
            "Huawei catalog collection requires huaweicloudsdkcore, "
            "huaweicloudsdkecs, and huaweicloudsdkiam"
        ) from exc

    return _HuaweiSdk(
        GlobalCredentials=GlobalCredentials,
        BasicCredentials=BasicCredentials,
        Region=Region,
        IamClient=IamClient,
        EcsClient=EcsClient,
        KeystoneListRegionsRequest=KeystoneListRegionsRequest,
        KeystoneListAuthProjectsRequest=KeystoneListAuthProjectsRequest,
        ListFlavorsRequest=ListFlavorsRequest,
        ListServerAzInfoRequest=ListServerAzInfoRequest,
    )


def _build_iam_client(access_key: str, secret_key: str, sdk: _HuaweiSdk) -> Any:
    from huaweicloudsdkcore.http.http_config import HttpConfig

    credentials = sdk.GlobalCredentials(access_key, secret_key)
    region = sdk.Region(IAM_REGION, IAM_ENDPOINT)
    return (
        sdk.IamClient.new_builder()
        .with_credentials(credentials)
        .with_region(region)
        .with_http_config(HttpConfig(timeout=HTTP_TIMEOUT_SECONDS))
        .build()
    )


def _build_ecs_client(
    access_key: str,
    secret_key: str,
    project_id: str,
    region_id: str,
    sdk: _HuaweiSdk,
) -> Any:
    from huaweicloudsdkcore.http.http_config import HttpConfig

    credentials = sdk.BasicCredentials(access_key, secret_key, project_id)
    # Construct the endpoint from IAM's current region list instead of relying
    # on the SDK's generated region table, which can lag newly opened regions.
    region = sdk.Region(
        region_id,
        f"https://ecs.{region_id}.myhuaweicloud.com",
    )
    return (
        sdk.EcsClient.new_builder()
        .with_credentials(credentials)
        .with_region(region)
        .with_http_config(HttpConfig(timeout=HTTP_TIMEOUT_SECONDS))
        .build()
    )


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _extra_value(extra_specs: Any, json_key: str, default: Any = None) -> Any:
    if extra_specs is None:
        return default
    if isinstance(extra_specs, Mapping):
        if json_key in extra_specs:
            return extra_specs[json_key]
        attribute = EXTRA_ATTRIBUTES.get(json_key)
        return extra_specs.get(attribute, default) if attribute else default
    attribute = EXTRA_ATTRIBUTES.get(json_key)
    if attribute and hasattr(extra_specs, attribute):
        value = getattr(extra_specs, attribute)
        return default if value is None else value
    return default


def _region_projects(
    region_models: Iterable[Any],
    project_models: Iterable[Any],
) -> list[tuple[str, str]]:
    region_ids: set[str] = set()
    for region in region_models:
        region_id = str(_value(region, "id", "") or "").strip()
        region_type = str(_value(region, "type", "public") or "public").lower()
        if (
            region_id
            and region_type == "public"
            and re.fullmatch(r"[a-z0-9][a-z0-9-]*", region_id)
        ):
            region_ids.add(region_id)

    project_by_region: dict[str, str] = {}
    for project in project_models:
        if _value(project, "enabled", True) is False:
            continue
        project_name = str(_value(project, "name", "") or "").strip()
        project_id = str(_value(project, "id", "") or "").strip()
        if project_name in region_ids and project_id:
            project_by_region.setdefault(project_name, project_id)

    return sorted(project_by_region.items())


def _list_zone_ids(client: Any, sdk: _HuaweiSdk) -> list[str]:
    response = client.list_server_az_info(sdk.ListServerAzInfoRequest())
    zones = _value(response, "availability_zones", []) or []
    return sorted(
        {
            str(_value(zone, "availability_zone_id", "") or "").strip()
            for zone in zones
            if (
                str(_value(zone, "availability_zone_id", "") or "").strip()
                and _is_public_shared_center_zone(zone)
            )
        }
    )


def _is_public_shared_center_zone(zone: Any) -> bool:
    """Exclude dedicated and edge AZs from the public flavor catalog."""

    zone_type = _optional_text(_value(zone, "type"))
    mode = _optional_text(_value(zone, "mode"))
    category = _optional_text(_value(zone, "category"))

    # The API omits default-valued fields in some regions. Treat a missing
    # classifier as unspecified, while rejecting every explicit non-public,
    # dedicated, HomeZone, or IES value.
    return (
        zone_type in {None, "center"}
        and mode in {None, "shared"}
        and category in {None, "0"}
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _is_region_forbidden(error: Exception) -> bool:
    return _value(error, "error_code") == "APIGW.0802"


def _warn_region_skipped(region_id: str) -> None:
    print(
        "::warning title=Huawei region skipped::"
        f"{region_id}: IAM user is forbidden in this region (APIGW.0802)"
    )


def _list_flavors(client: Any, sdk: _HuaweiSdk) -> Iterable[Any]:
    marker: str | None = None
    seen_markers: set[str] = set()

    while True:
        request = sdk.ListFlavorsRequest(limit=PAGE_SIZE, marker=marker)
        response = client.list_flavors(request)
        page = list(_value(response, "flavors", []) or [])
        for flavor in page:
            yield flavor

        if len(page) < PAGE_SIZE:
            return

        next_marker = str(_value(page[-1], "id", "") or "").strip()
        if not next_marker or next_marker in seen_markers:
            raise RuntimeError("Huawei ECS flavor pagination did not advance")
        seen_markers.add(next_marker)
        marker = next_marker


def _parse_zone_states(value: Any) -> dict[str, str]:
    text = str(value or "")
    return {
        zone.strip(): state.strip().lower()
        for zone, state in re.findall(r"([^,()\s]+)\s*\(\s*([^,()\s]+)\s*\)", text)
    }


def _normal_charge_supported(extra_specs: Any) -> bool:
    raw = str(_extra_value(extra_specs, "cond:operation:charge", "") or "")
    if not raw.strip():
        return True
    modes = set(re.findall(r"[a-z]+", raw.lower()))
    return bool(modes & NORMAL_CHARGE_MODES)


def _available_zones(extra_specs: Any, known_zones: Iterable[str]) -> tuple[bool, list[str]]:
    default_state = str(
        _extra_value(extra_specs, "cond:operation:status", "normal") or "normal"
    ).strip().lower()
    overrides = _parse_zone_states(
        _extra_value(extra_specs, "cond:operation:az", "")
    )
    candidates = set(known_zones) | set(overrides)
    zones = sorted(
        zone
        for zone in candidates
        if overrides.get(zone, default_state) in AVAILABLE_STATES
    )
    if candidates:
        return bool(zones), zones
    return default_state in AVAILABLE_STATES, []


def _is_false(value: Any) -> bool:
    return value is False or str(value).strip().lower() in {"false", "0", "no"}


def _is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _architecture(extra_specs: Any, instance_type: str) -> str:
    explicit = str(
        _extra_value(extra_specs, "ecs:instance_architecture", "") or ""
    ).lower()
    processor = str(_extra_value(extra_specs, "info:cpu:name", "") or "").lower()
    text = f"{explicit} {processor} {instance_type.lower()}"
    if any(token in text for token in ("arm64", "aarch64", "kunpeng", "arm")):
        return "arm64"
    # Huawei currently only emits ecs:instance_architecture for Arm flavors;
    # the documented absence of the field denotes the regular x86 catalog.
    return "x86_64"


def _format_rate(raw: Any) -> str | None:
    rate = number(raw)
    if rate <= 0:
        return None
    if rate >= 1000:
        return f"{rate / 1000:g} Gbps"
    return f"{rate:g} Mbps"


def _network_performance(extra_specs: Any) -> str:
    maximum = _format_rate(
        _extra_value(extra_specs, "quota:max_rate")
        or _extra_value(extra_specs, "instance_vnic:instance_bandwidth")
    )
    minimum = _format_rate(_extra_value(extra_specs, "quota:min_rate"))
    pps = number(_extra_value(extra_specs, "quota:max_pps"))

    if maximum and minimum:
        text = f"{maximum} max / {minimum} assured"
    elif maximum:
        text = f"Up to {maximum}"
    else:
        text = "Not published"
    if packet_rate := format_packet_rate(pps):
        text += f"; {packet_rate}"
    return text


def _local_storage(extra_specs: Any) -> str:
    if _extra_value(extra_specs, "quota:nvme_ssd"):
        return "Local NVMe SSD"
    if _extra_value(extra_specs, "quota:local_disk"):
        return "Local disks"
    return "EVS cloud disks"


def _counts_from_json(value: Any) -> list[float]:
    if isinstance(value, Mapping):
        counts = [number(value.get("count"))] if "count" in value else []
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                counts.extend(_counts_from_json(child))
        return counts
    if isinstance(value, (list, tuple)):
        counts: list[float] = []
        for child in value:
            counts.extend(_counts_from_json(child))
        return counts
    return []


def _gpu_count(extra_specs: Any) -> float:
    # `quota:gpu` is the GPU model name (for example, "NVIDIA V100"), not a
    # numeric quota.  Parsing digits from it would turn V100 into 100 GPUs.
    candidates: list[float] = []
    gpu_info = _extra_value(extra_specs, "info:gpus")
    if gpu_info:
        try:
            candidates.extend(_counts_from_json(json.loads(str(gpu_info))))
        except (TypeError, ValueError):
            match = re.search(
                r"(?:count|gpu)[^0-9]*(\d+(?:\.\d+)?)",
                str(gpu_info),
                re.I,
            )
            if match:
                candidates.append(number(match.group(1)))

    for key in ("pci_passthrough:alias", "pci_passthrough:gpu_specs"):
        raw = str(_extra_value(extra_specs, key, "") or "")
        match = re.search(r":(\d+(?:\.\d+)?)(?:\s*,|\s*$)", raw)
        if match:
            candidates.append(number(match.group(1)))
    return max(candidates, default=0)


def _record_for_flavor(
    flavor: Any,
    region_id: str,
    known_zones: Iterable[str],
) -> dict[str, Any] | None:
    instance_type = str(
        _value(flavor, "id") or _value(flavor, "name") or ""
    ).strip()
    vcpu = number(_value(flavor, "vcpus"))
    ram_mib = number(_value(flavor, "ram"))
    if not instance_type or vcpu <= 0 or ram_mib <= 0:
        return None
    if _is_true(_value(flavor, "os_flv_disable_ddisabled", False)):
        return None
    public = _value(flavor, "os_flavor_accessis_public", True)
    if _is_false(public):
        return None

    extra_specs = _value(flavor, "os_extra_specs") or {}
    region_available, zones = _available_zones(extra_specs, known_zones)
    regular_purchase_available = (
        _normal_charge_supported(extra_specs) and region_available
    )

    performance = str(
        _extra_value(extra_specs, "ecs:performancetype")
        or _extra_value(extra_specs, "hws:performancetype")
        or ""
    ).strip().lower()
    performance_name = PERFORMANCE_NAMES.get(
        performance,
        performance.replace("_", " ").title() if performance else "",
    )
    family = family_from_instance_type(instance_type)
    architecture = _architecture(extra_specs, instance_type)
    processor = str(_extra_value(extra_specs, "info:cpu:name", "") or "").strip()
    if not processor:
        processor = (
            "Huawei Kunpeng"
            if architecture == "arm64"
            else "Provider-managed x86 CPU"
        )

    record: dict[str, Any] = {
        "instanceType": instance_type,
        "family": family,
        "familyName": (
            f"{performance_name} {family}" if performance_name else family
        ),
        "vCPU": int(vcpu) if vcpu.is_integer() else vcpu,
        "memoryGiB": round(ram_mib / 1024, 4),
        "architecture": architecture,
        "processor": processor,
        "networkPerformance": _network_performance(extra_specs),
        "localStorage": _local_storage(extra_specs),
        "sourceUrl": SOURCE_URL,
        "regions": [region_id] if regular_purchase_available else [],
        "zones": zones if regular_purchase_available else [],
    }
    gpu_count = _gpu_count(extra_specs)
    if gpu_count > 0:
        record["gpuCount"] = gpu_count
    if performance_name or performance:
        record["categoryHint"] = performance_name or performance
    return record


def fetch() -> dict[str, Any]:
    """Return public Huawei ECS flavors and regular-purchase availability."""

    access_key, secret_key = require_env(
        "HUAWEI_ACCESS_KEY_ID",
        "HUAWEI_SECRET_ACCESS_KEY",
    )
    sdk = _load_sdk()
    iam_client = _build_iam_client(access_key, secret_key, sdk)

    region_response = iam_client.keystone_list_regions(
        sdk.KeystoneListRegionsRequest()
    )
    project_response = iam_client.keystone_list_auth_projects(
        sdk.KeystoneListAuthProjectsRequest()
    )
    region_projects = _region_projects(
        _value(region_response, "regions", []) or [],
        _value(project_response, "projects", []) or [],
    )

    records: list[dict[str, Any]] = []
    regions: list[str] = []
    all_zones: set[str] = set()
    skipped_regions: list[str] = []
    for region_id, project_id in region_projects:
        try:
            ecs_client = _build_ecs_client(
                access_key,
                secret_key,
                project_id,
                region_id,
                sdk,
            )
            zone_ids = _list_zone_ids(ecs_client, sdk)
            region_records: list[dict[str, Any]] = []
            for flavor in _list_flavors(ecs_client, sdk):
                record = _record_for_flavor(flavor, region_id, zone_ids)
                if record is not None:
                    region_records.append(record)
        except Exception as error:
            if not _is_region_forbidden(error):
                raise
            skipped_regions.append(region_id)
            _warn_region_skipped(region_id)
            continue

        regions.append(region_id)
        all_zones.update(zone_ids)
        records.extend(region_records)

    result = provider_result("huawei", records, regions, all_zones)
    result["skippedRegions"] = skipped_regions
    return result
