from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from scripts.china_cloud.common import (
    family_from_instance_type,
    format_packet_rate,
    log_progress,
    number,
    provider_result,
    require_env,
)


PAGE_SIZE = 1000
IAM_REGION = "cn-north-4"
IAM_ENDPOINT = "https://iam.cn-north-4.myhuaweicloud.com"
BSS_REGION = "cn-north-1"
BSS_ENDPOINT = "https://bss.myhuaweicloud.com"
PRICE_BATCH_SIZE = 100
ECS_CLOUD_SERVICE_TYPE = "hws.service.type.ec2"
ECS_RESOURCE_TYPE = "hws.resource.type.vm"
HOURLY_USAGE_MEASURE_ID = 4
SOURCE_URL = (
    "https://support.huaweicloud.com/api-ecs/zh-cn_topic_0020212656.html"
)

# `obt` is an orderable public-beta state. The sold-out and withdrawn variants
# are deliberately absent from this set.
AVAILABLE_STATES = {"normal", "promotion", "obt"}
NORMAL_CHARGE_MODES = {"demand", "period"}
HTTP_TIMEOUT_SECONDS = (5, 20)
PRICE_HTTP_TIMEOUT_SECONDS = (3, 8)

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
    BssClient: Any
    KeystoneListRegionsRequest: Any
    KeystoneListAuthProjectsRequest: Any
    ListFlavorsRequest: Any
    ListServerAzInfoRequest: Any
    ListOnDemandResourceRatingsRequest: Any
    RateOnDemandReq: Any
    DemandProductInfo: Any


def _load_sdk() -> _HuaweiSdk:
    """Import SDKs lazily so offline unit tests do not require vendor wheels."""

    try:
        from huaweicloudsdkcore.auth.credentials import (
            BasicCredentials,
            GlobalCredentials,
        )
        from huaweicloudsdkcore.region.region import Region
        from huaweicloudsdkbss.v2 import (
            BssClient,
            DemandProductInfo,
            ListOnDemandResourceRatingsRequest,
            RateOnDemandReq,
        )
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
            "huaweicloudsdkbss, huaweicloudsdkecs, and huaweicloudsdkiam"
        ) from exc

    return _HuaweiSdk(
        GlobalCredentials=GlobalCredentials,
        BasicCredentials=BasicCredentials,
        Region=Region,
        IamClient=IamClient,
        EcsClient=EcsClient,
        BssClient=BssClient,
        KeystoneListRegionsRequest=KeystoneListRegionsRequest,
        KeystoneListAuthProjectsRequest=KeystoneListAuthProjectsRequest,
        ListFlavorsRequest=ListFlavorsRequest,
        ListServerAzInfoRequest=ListServerAzInfoRequest,
        ListOnDemandResourceRatingsRequest=ListOnDemandResourceRatingsRequest,
        RateOnDemandReq=RateOnDemandReq,
        DemandProductInfo=DemandProductInfo,
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


def _build_bss_client(access_key: str, secret_key: str, sdk: _HuaweiSdk) -> Any:
    from huaweicloudsdkcore.http.http_config import HttpConfig

    credentials = sdk.GlobalCredentials(access_key, secret_key)
    region = sdk.Region(BSS_REGION, BSS_ENDPOINT)
    return (
        sdk.BssClient.new_builder()
        .with_credentials(credentials)
        .with_region(region)
        .with_http_config(HttpConfig(timeout=PRICE_HTTP_TIMEOUT_SECONDS))
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


def _public_price_amount(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return format(amount.normalize(), "f")


def _price_error_texts(error: Exception) -> list[str]:
    texts: list[str] = []
    for value in (_value(error, "error_msg"), str(error)):
        text = str(value or "").replace(r'\"', '"').replace(r"\'", "'")
        if text and text not in texts:
            texts.append(text)
    return texts


def _is_price_product_not_found(error: Exception) -> bool:
    """Return whether BSS rejected an unknown product specification."""

    error_code = str(_value(error, "error_code", "") or "").strip()
    if error_code == "CBC.6006":
        return True
    if error_code != "CBC.99006006":
        return False

    # The Huawei SDK wraps BSS's real CBC.6006 response in CBC.99006006.
    # Require the nested error-code field as well: CBC.99006006 is a generic
    # wrapper and must not make unrelated billing failures look skippable.
    nested_code = re.compile(
        r"(?:\[error_code\]|[\"']error_code[\"'])\s*:\s*"
        r"[\"']?CBC\.6006\b",
        re.IGNORECASE,
    )
    return any(nested_code.search(text) for text in _price_error_texts(error))


def _missing_price_instance_type(
    error: Exception,
    batch: Iterable[str],
) -> str | None:
    """Extract the exact missing flavor named by a CBC.6006 response."""

    instance_type_by_spec = {
        f"{instance_type}.linux": instance_type for instance_type in batch
    }
    missing_product = re.compile(
        r"\bcan(?:\s+not|not)\s+find\s+product\s*[:=]?\s*"
        r"[\"']?([a-z0-9][a-z0-9._-]*\.linux)\b",
        re.IGNORECASE,
    )
    for text in _price_error_texts(error):
        match = missing_product.search(text)
        if match:
            instance_type = instance_type_by_spec.get(match.group(1))
            if instance_type is not None:
                return instance_type
    return None


def _warn_price_product_skipped(region_id: str, instance_type: str) -> None:
    print(
        "::warning title=Huawei price skipped::"
        f"{region_id}/{instance_type}: BSS product not found (CBC.6006)"
    )


def _regional_on_demand_prices(
    client: Any,
    sdk: _HuaweiSdk,
    project_id: str,
    region_id: str,
    records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, str]]]:
    """Query public Linux hourly prices for sellable flavors in one region."""

    instance_types = sorted(
        {
            str(record.get("instanceType") or "").strip()
            for record in records
            if region_id in (record.get("regions") or [])
            and str(record.get("instanceType") or "").strip()
        }
    )
    prices: dict[str, dict[str, dict[str, str]]] = {}

    def query_batch(batch: list[str]) -> None:
        instance_type_by_id = {
            str(index): instance_type
            for index, instance_type in enumerate(batch, start=1)
        }
        product_infos = [
            sdk.DemandProductInfo(
                id=request_id,
                cloud_service_type=ECS_CLOUD_SERVICE_TYPE,
                resource_type=ECS_RESOURCE_TYPE,
                resource_spec=f"{instance_type}.linux",
                region=region_id,
                usage_factor="Duration",
                usage_value=Decimal("1"),
                usage_measure_id=HOURLY_USAGE_MEASURE_ID,
                subscription_num=1,
            )
            for request_id, instance_type in instance_type_by_id.items()
        ]
        body = sdk.RateOnDemandReq(
            project_id=project_id,
            inquiry_precision=1,
            product_infos=product_infos,
        )
        try:
            response = client.list_on_demand_resource_ratings(
                sdk.ListOnDemandResourceRatingsRequest(body=body)
            )
        except Exception as error:
            # One retired or otherwise unknown flavor makes BSS reject the
            # entire request. Remove the named product when possible; otherwise
            # bisect this documented product-not-found failure. Permissions,
            # transport failures, throttling, and every other BSS error remain
            # fatal and propagate unchanged.
            if not _is_price_product_not_found(error):
                raise
            missing_instance_type = _missing_price_instance_type(error, batch)
            if missing_instance_type is not None:
                _warn_price_product_skipped(region_id, missing_instance_type)
                remaining = [
                    instance_type
                    for instance_type in batch
                    if instance_type != missing_instance_type
                ]
                if remaining:
                    query_batch(remaining)
                return
            if len(batch) == 1:
                _warn_price_product_skipped(region_id, batch[0])
                return
            midpoint = len(batch) // 2
            query_batch(batch[:midpoint])
            query_batch(batch[midpoint:])
            return

        currency = str(_value(response, "currency", "") or "CNY").upper()
        if currency != "CNY":
            raise RuntimeError(
                f"Huawei BSS returned unexpected pricing currency {currency!r}"
            )

        for result in _value(response, "product_rating_results", []) or []:
            request_id = str(_value(result, "id", "") or "")
            instance_type = instance_type_by_id.get(request_id)
            # Use the public list price only. `amount`, `discount_amount`, and
            # `discount_rating_results` are account-specific and intentionally
            # ignored even when the caller can view them.
            amount = _public_price_amount(
                _value(result, "official_website_amount")
            )
            if instance_type and amount is not None:
                prices[instance_type] = {
                    region_id: {
                        "amount": amount,
                        "currency": "CNY",
                        "unit": "hour",
                    }
                }

    for offset in range(0, len(instance_types), PRICE_BATCH_SIZE):
        query_batch(instance_types[offset : offset + PRICE_BATCH_SIZE])

    return prices


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
    bss_client = _build_bss_client(access_key, secret_key, sdk)

    log_progress("huawei", "iam_discovery", "started")
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
    log_progress(
        "huawei", "iam_discovery", "completed", regions=len(region_projects)
    )

    records: list[dict[str, Any]] = []
    regions: list[str] = []
    all_zones: set[str] = set()
    skipped_regions: list[str] = []
    for region_id, project_id in region_projects:
        log_progress("huawei", "region_catalog", "started", region=region_id)
        try:
            ecs_client = _build_ecs_client(
                access_key,
                secret_key,
                project_id,
                region_id,
                sdk,
            )
            log_progress("huawei", "zones", "started", region=region_id)
            zone_ids = _list_zone_ids(ecs_client, sdk)
            log_progress(
                "huawei", "zones", "completed", region=region_id, count=len(zone_ids)
            )
            region_records: list[dict[str, Any]] = []
            log_progress("huawei", "flavors", "started", region=region_id)
            for flavor in _list_flavors(ecs_client, sdk):
                record = _record_for_flavor(flavor, region_id, zone_ids)
                if record is not None:
                    region_records.append(record)
            log_progress(
                "huawei",
                "flavors",
                "completed",
                region=region_id,
                records=len(region_records),
            )
            log_progress(
                "huawei",
                "pricing",
                "started",
                region=region_id,
                instance_types=len(region_records),
            )
            regional_prices = _regional_on_demand_prices(
                bss_client,
                sdk,
                project_id,
                region_id,
                region_records,
            )
            log_progress(
                "huawei",
                "pricing",
                "completed",
                region=region_id,
                priced_instance_types=len(regional_prices),
            )
            for record in region_records:
                if price := regional_prices.get(record["instanceType"]):
                    record["onDemandPrices"] = price
        except Exception as error:
            if not _is_region_forbidden(error):
                raise
            skipped_regions.append(region_id)
            _warn_region_skipped(region_id)
            log_progress("huawei", "region_catalog", "skipped", region=region_id)
            continue

        regions.append(region_id)
        all_zones.update(zone_ids)
        records.extend(region_records)
        log_progress(
            "huawei",
            "region_catalog",
            "completed",
            region=region_id,
            records=len(region_records),
        )

    result = provider_result("huawei", records, regions, all_zones)
    result["skippedRegions"] = skipped_regions
    return result
