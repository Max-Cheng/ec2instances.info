from __future__ import annotations

import importlib
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from scripts.china_cloud.common import (
    format_packet_rate,
    integer,
    log_progress,
    nonempty,
    number,
    provider_result,
    require_env,
)


SOURCE_URL = "https://cloud.tencent.com/document/product/213/15749"
REQUEST_TIMEOUT_SECONDS = 20
OPTIONAL_PRICE_REQUEST_TIMEOUT_SECONDS = 8
ONE_YEAR_HOURS = Decimal(365 * 24)
EFFECTIVE_HOURLY_QUANTUM = Decimal("0.00000001")
OPTIONAL_PRICE_WORKERS = 8


def prepare() -> None:
    """Load the SDK serially before provider network work becomes concurrent."""

    from tencentcloud.common import credential  # noqa: F401
    from tencentcloud.common.profile import client_profile  # noqa: F401
    from tencentcloud.common.profile import http_profile  # noqa: F401
    from tencentcloud.cvm.v20170312 import cvm_client  # noqa: F401
    from tencentcloud.cvm.v20170312 import models as cvm_models  # noqa: F401
    from tencentcloud.region.v20220627 import models as region_models  # noqa: F401
    from tencentcloud.region.v20220627 import region_client  # noqa: F401


def _client_profile(
    endpoint: str,
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> Any:
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile

    http_profile = HttpProfile(
        protocol="https",
        endpoint=endpoint,
        reqMethod="POST",
        reqTimeout=request_timeout_seconds,
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


def _make_cvm_client(
    secret_id: str,
    secret_key: str,
    region: str,
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> Any:
    from tencentcloud.common import credential
    from tencentcloud.cvm.v20170312.cvm_client import CvmClient

    return CvmClient(
        credential.Credential(secret_id, secret_key),
        region,
        _client_profile("cvm.tencentcloudapi.com", request_timeout_seconds),
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
    if packet_rate := format_packet_rate(packets * 10_000):
        details.append(packet_rate)
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


def _public_hourly_price(item: dict[str, Any]) -> Decimal | None:
    price = item.get("Price")
    if not isinstance(price, dict):
        return None

    # ItemPrice.UnitPrice is Tencent's original postpaid price. Do not fall
    # back to UnitPriceDiscount (account discount) or OriginalPrice (prepaid).
    if str(price.get("ChargeUnit") or "").strip().upper() != "HOUR":
        return None
    value = price.get("UnitPrice")
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return amount


def _public_spot_hourly_price(item: dict[str, Any]) -> Decimal | None:
    price = item.get("Price")
    if not isinstance(price, dict):
        return None

    # For a SPOTPAID catalog response, UnitPriceDiscount is the current public
    # market price. UnitPrice remains the regular postpaid list price, so using
    # it here would make the spot column duplicate the on-demand column.
    if str(price.get("ChargeUnit") or "").strip().upper() != "HOUR":
        return None
    value = price.get("UnitPriceDiscount")
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return amount


def _public_one_year_subscription_total(item: dict[str, Any]) -> Decimal | None:
    price = item.get("Price")
    if not isinstance(price, dict):
        return None

    # ItemPrice.OriginalPriceOneYear is Tencent's public one-year prepaid
    # total. DiscountPriceOneYear and DiscountOneYear can be account-specific,
    # so they must never be used for a public catalog.
    value = price.get("OriginalPriceOneYear")
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return amount


def _matches_charge_type(item: dict[str, Any], expected: str) -> bool:
    charge_type = str(item.get("InstanceChargeType") or "").strip().upper()
    # Optional billing data is published only when Tencent explicitly echoes
    # the requested mode; an ambiguous response must never be mislabeled Spot.
    return charge_type == expected


def _declares_charge_type(items: list[dict[str, Any]], expected: str) -> bool:
    return any(
        str(item.get("InstanceChargeType") or "").strip().upper() == expected
        for item in items
    )


def _regional_on_demand_prices(
    quotas: list[dict[str, Any]],
    region: str,
) -> dict[str, dict[str, dict[str, str]]]:
    lowest_by_type: dict[str, Decimal] = {}
    for quota in quotas:
        if not _is_sellable(quota):
            continue
        instance_type = str(quota.get("InstanceType") or "").strip()
        amount = _public_hourly_price(quota)
        if not instance_type or amount is None:
            continue
        current = lowest_by_type.get(instance_type)
        if current is None or amount < current:
            lowest_by_type[instance_type] = amount

    return {
        instance_type: {
            region: {
                "amount": format(amount.normalize(), "f"),
                "currency": "CNY",
                "unit": "hour",
            }
        }
        for instance_type, amount in sorted(lowest_by_type.items())
    }


def _regional_subscription_prices(
    quotas: list[dict[str, Any]],
    region: str,
) -> dict[str, dict[str, dict[str, str]]]:
    lowest_by_type: dict[str, Decimal] = {}
    for quota in quotas:
        # OriginalPriceOneYear is the public one-year prepaid list total. Never
        # use DiscountPriceOneYear, which may include account-specific terms.
        if not _is_sellable(quota) or not _matches_charge_type(quota, "PREPAID"):
            continue
        instance_type = str(quota.get("InstanceType") or "").strip()
        total = _public_one_year_subscription_total(quota)
        if not instance_type or total is None:
            continue
        current = lowest_by_type.get(instance_type)
        if current is None or total < current:
            lowest_by_type[instance_type] = total

    return {
        instance_type: {
            region: {
                "amount": format(
                    (total / ONE_YEAR_HOURS)
                    .quantize(EFFECTIVE_HOURLY_QUANTUM, rounding=ROUND_HALF_UP)
                    .normalize(),
                    "f",
                ),
                "totalAmount": format(total.normalize(), "f"),
                "currency": "CNY",
                "unit": "hour",
                "term": "1-year",
                "payment": "all-upfront",
            }
        }
        for instance_type, total in sorted(lowest_by_type.items())
    }


def _regional_spot_prices(
    quotas: list[dict[str, Any]],
    region: str,
) -> dict[str, dict[str, dict[str, str]]]:
    lowest_by_type: dict[str, tuple[Decimal, str]] = {}
    for quota in quotas:
        if not _is_sellable(quota) or not _matches_charge_type(quota, "SPOTPAID"):
            continue
        instance_type = str(quota.get("InstanceType") or "").strip()
        zone = str(quota.get("Zone") or "").strip()
        amount = _public_spot_hourly_price(quota)
        if not instance_type or amount is None:
            continue
        current = lowest_by_type.get(instance_type)
        if current is None or (amount, zone) < current:
            lowest_by_type[instance_type] = (amount, zone)

    prices: dict[str, dict[str, dict[str, str]]] = {}
    for instance_type, (amount, zone) in sorted(lowest_by_type.items()):
        price = {
            "amount": format(amount.normalize(), "f"),
            "currency": "CNY",
            "unit": "hour",
        }
        if zone:
            price["zone"] = zone
        prices[instance_type] = {region: price}
    return prices


def _fetch_charge_type_quotas(
    client: Any,
    region: str,
    charge_types: str | tuple[str, ...],
) -> list[dict[str, Any]]:
    values = [charge_types] if isinstance(charge_types, str) else list(charge_types)
    stage = "optional_prices" if len(values) > 1 else f"{values[0].lower()}_prices"
    log_progress("tencent", stage, "started", region=region)
    try:
        payload = _call(
            client,
            "tencentcloud.cvm.v20170312.models",
            "DescribeZoneInstanceConfigInfosRequest",
            "DescribeZoneInstanceConfigInfos",
            Filters=[
                {
                    "Name": "instance-charge-type",
                    "Values": values,
                }
            ],
        )
    except Exception as error:
        # Subscription and spot prices are optional enrichment. A regional
        # pricing-mode failure must not discard otherwise valid inventory and
        # on-demand prices from the same API.
        log_progress(
            "tencent",
            stage,
            "failed",
            region=region,
            error=error.__class__.__name__,
        )
        return []

    quotas = _items(payload, "InstanceTypeQuotaSet")
    log_progress("tencent", stage, "completed", region=region, quotas=len(quotas))
    return quotas


def _merge_region_prices(
    destination: dict[str, dict[str, dict[str, str]]],
    source: dict[str, dict[str, dict[str, str]]],
) -> None:
    for instance_type, prices in source.items():
        destination.setdefault(instance_type, {}).update(prices)


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
    log_progress("tencent", "regions", "started")
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
    log_progress("tencent", "regions", "completed", count=len(regions))

    all_zones: set[str] = set()
    records: list[dict[str, Any]] = []
    subscription_prices: dict[str, dict[str, dict[str, str]]] = {}
    spot_prices: dict[str, dict[str, dict[str, str]]] = {}
    optional_price_regions: list[str] = []
    for region in regions:
        region_record_start = len(records)
        log_progress("tencent", "region_catalog", "started", region=region)
        client = _make_cvm_client(secret_id, secret_key, region)
        log_progress("tencent", "zones", "started", region=region)
        zone_payload = _call(
            client,
            "tencentcloud.cvm.v20170312.models",
            "DescribeZonesRequest",
            "DescribeZones",
        )
        region_zones = {
            zone
            for item in _items(zone_payload, "ZoneSet")
            if _available_or_unspecified(item, "ZoneState")
            if (zone := str(item.get("Zone") or "").strip())
        }
        all_zones.update(region_zones)
        log_progress(
            "tencent", "zones", "completed", region=region, count=len(region_zones)
        )

        log_progress("tencent", "instance_types", "started", region=region)
        spec_payload = _call(
            client,
            "tencentcloud.cvm.v20170312.models",
            "DescribeInstanceTypeConfigsRequest",
            "DescribeInstanceTypeConfigs",
        )
        specs = _items(spec_payload, "InstanceTypeConfigSet")
        log_progress(
            "tencent",
            "instance_types",
            "completed",
            region=region,
            count=len(specs),
        )
        log_progress("tencent", "availability_prices", "started", region=region)
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
        quotas = _items(quota_payload, "InstanceTypeQuotaSet")
        regional_prices = _regional_on_demand_prices(quotas, region)
        log_progress(
            "tencent",
            "availability_prices",
            "completed",
            region=region,
            quotas=len(quotas),
            priced_instance_types=len(regional_prices),
        )

        # Price fields are billing-mode specific. Only request optional modes
        # after the API has explicitly echoed the POSTPAID_BY_HOUR filter; this
        # avoids interpreting ambiguous legacy responses as public catalog data.
        if _declares_charge_type(quotas, "POSTPAID_BY_HOUR"):
            optional_price_regions.append(region)
        else:
            log_progress(
                "tencent",
                "optional_prices",
                "skipped",
                region=region,
                reason="charge_type_not_declared",
            )

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
                if price := regional_prices.get(record["instanceType"]):
                    record["onDemandPrices"] = price
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
                if price := regional_prices.get(record["instanceType"]):
                    record["onDemandPrices"] = price
                records.append(record)

        log_progress(
            "tencent",
            "region_catalog",
            "completed",
            region=region,
            records=len(records) - region_record_start,
        )

    # The base Tencent catalog is already a relatively slow sequential scan.
    # Fetch PREPAID and SPOTPAID together in one filtered request per region.
    # This preserves the same request count as spot-only enrichment while
    # keeping the slow base scan inside the Pages workflow's 120-second guard.
    if optional_price_regions:
        log_progress(
            "tencent",
            "optional_price_enrichment",
            "started",
            regions=len(optional_price_regions),
            workers=min(OPTIONAL_PRICE_WORKERS, len(optional_price_regions)),
        )

        def fetch_region_optional_prices(
            region: str,
        ) -> tuple[
            dict[str, dict[str, dict[str, str]]],
            dict[str, dict[str, dict[str, str]]],
        ]:
            client = _make_cvm_client(
                secret_id,
                secret_key,
                region,
                request_timeout_seconds=OPTIONAL_PRICE_REQUEST_TIMEOUT_SECONDS,
            )
            quotas = _fetch_charge_type_quotas(
                client,
                region,
                ("PREPAID", "SPOTPAID"),
            )
            return (
                _regional_subscription_prices(quotas, region),
                _regional_spot_prices(quotas, region),
            )

        with ThreadPoolExecutor(
            max_workers=min(OPTIONAL_PRICE_WORKERS, len(optional_price_regions))
        ) as executor:
            futures = {
                executor.submit(fetch_region_optional_prices, region): region
                for region in optional_price_regions
            }
            for future in as_completed(futures):
                region = futures[future]
                try:
                    regional_subscription_prices, regional_spot_prices = (
                        future.result()
                    )
                except Exception as error:
                    log_progress(
                        "tencent",
                        "optional_prices",
                        "failed",
                        region=region,
                        error=error.__class__.__name__,
                    )
                    continue
                _merge_region_prices(
                    subscription_prices,
                    regional_subscription_prices,
                )
                _merge_region_prices(spot_prices, regional_spot_prices)
        log_progress(
            "tencent",
            "optional_price_enrichment",
            "completed",
            regions=len(optional_price_regions),
            spot_priced_instance_types=len(spot_prices),
            subscription_priced_instance_types=len(subscription_prices),
        )

    result = provider_result("tencent", records, regions, all_zones)
    for instance in result["instances"]:
        instance_type = str(instance.get("instanceType") or "")
        available_regions = set(instance.get("regions") or [])
        available_zones = set(instance.get("zones") or [])
        for field, prices_by_type in (
            ("subscriptionPrices", subscription_prices),
            ("spotPrices", spot_prices),
        ):
            prices = {
                region: price
                for region, price in prices_by_type.get(instance_type, {}).items()
                if region in available_regions
                and (
                    field != "spotPrices"
                    or not price.get("zone")
                    or price.get("zone") in available_zones
                )
            }
            if prices:
                instance[field] = dict(sorted(prices.items()))
    return result
