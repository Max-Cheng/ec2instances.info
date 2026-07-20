from __future__ import annotations

import importlib
import json
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scripts.china_cloud.common import (
    format_packet_rate,
    integer,
    nonempty,
    number,
    provider_result,
    require_env,
)


SOURCE_URL = (
    "https://help.aliyun.com/en/ecs/developer-reference/"
    "api-ecs-2014-05-26-describeinstancetypes"
)
BOOTSTRAP_REGION = "cn-hangzhou"
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 20
PRICE_CONNECT_TIMEOUT_SECONDS = 3
PRICE_READ_TIMEOUT_SECONDS = 8
PRICE_TIME_BUDGET_SECONDS = 45
PRICE_WORKERS = 12
AVAILABILITY_WORKERS = 8
# DescribePrice is user-throttled. Keep headroom below the documented 20 QPS.
PRICE_QUERIES_PER_SECOND = 18
PREVIOUS_CATALOG_ENV = "CHINA_CLOUD_PREVIOUS_CATALOG"
DEFAULT_PREVIOUS_CATALOG = Path("/tmp/china-clouds-previous.json")


def _make_client(access_key_id: str, access_key_secret: str, region_id: str) -> Any:
    from aliyunsdkcore.client import AcsClient

    return AcsClient(
        access_key_id,
        access_key_secret,
        region_id,
        auto_retry=True,
        max_retry_time=1,
        port=443,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        timeout=READ_TIMEOUT_SECONDS,
        debug=False,
    )


def _make_price_client(
    access_key_id: str,
    access_key_secret: str,
    region_id: str,
) -> Any:
    """Build a fail-fast client so optional prices cannot consume the refresh."""

    from aliyunsdkcore.client import AcsClient

    return AcsClient(
        access_key_id,
        access_key_secret,
        region_id,
        auto_retry=False,
        max_retry_time=0,
        port=443,
        connect_timeout=PRICE_CONNECT_TIMEOUT_SECONDS,
        timeout=PRICE_READ_TIMEOUT_SECONDS,
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


def _bandwidth(value: Any) -> str:
    # Despite the documented kbit/s unit, Alibaba emits 1024-based steps:
    # 1,024,000 represents the marketed 1 Gbps rather than 1.024 Gbps.
    mbps = number(value) / 1024
    if mbps <= 0:
        return ""
    if mbps >= 1000:
        return f"{_compact(mbps / 1000)} Gbps"
    return f"{_compact(mbps)} Mbps"


def _network_performance(spec: dict[str, Any]) -> str:
    bandwidth = _bandwidth(
        max(
            number(spec.get("InstanceBandwidthRx")),
            number(spec.get("InstanceBandwidthTx")),
        )
    )
    packets = max(
        number(spec.get("InstancePpsRx")),
        number(spec.get("InstancePpsTx")),
    )
    details: list[str] = []
    if bandwidth:
        details.append(f"Up to {bandwidth}")
    if packet_rate := format_packet_rate(packets):
        details.append(packet_rate)
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

    def fetch_region(region_id: str) -> tuple[str, set[str], list[tuple[str, str]]]:
        client = _make_client(access_key_id, access_key_secret, region_id)
        zone_payload = _invoke(
            client,
            "DescribeZones",
            InstanceChargeType="PostPaid",
            SpotStrategy="NoSpot",
            AcceptLanguage="en-US",
        )
        region_zones = {
            zone_id
            for item in _nested_list(zone_payload, "Zones", "Zone")
            if (zone_id := str(item.get("ZoneId") or "").strip())
        }

        resource_payload = _invoke(
            client,
            "DescribeAvailableResource",
            DestinationResource="InstanceType",
            ResourceType="instance",
            InstanceChargeType="PostPaid",
        )
        stocked: list[tuple[str, str]] = []
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
                    stocked.append((instance_type, zone_id))
        return region_id, region_zones, stocked

    with ThreadPoolExecutor(
        max_workers=min(AVAILABILITY_WORKERS, max(1, len(region_ids)))
    ) as executor:
        futures = [executor.submit(fetch_region, region_id) for region_id in region_ids]
        for future in as_completed(futures):
            region_id, region_zones, stocked = future.result()
            all_zones.update(region_zones)
            for instance_type, zone_id in stocked:
                available[instance_type]["regions"].add(region_id)
                if zone_id:
                    available[instance_type]["zones"].add(zone_id)

    return available, all_zones


def _amount_string(value: Any) -> str | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _extract_on_demand_price(payload: dict[str, Any]) -> dict[str, str] | None:
    price_info = payload.get("PriceInfo")
    if not isinstance(price_info, dict):
        return None
    price = price_info.get("Price")
    if not isinstance(price, dict):
        return None
    currency = str(price.get("Currency") or "").strip().upper()
    if currency not in {"CNY", "USD"}:
        return None

    # The aggregate price can include image, disk, or bandwidth components when
    # callers add them later. Prefer the component explicitly identified as the
    # instance type, while retaining the documented aggregate fallback for the
    # current zero-bandwidth, no-image request.
    original_price: Any = None
    for detail in _nested_list(price, "DetailInfos", "DetailInfo"):
        resource = str(detail.get("Resource") or "").strip().lower()
        if resource in {"instancetype", "instance"}:
            original_price = detail.get("OriginalPrice")
            break
    if original_price is None:
        original_price = price.get("OriginalPrice")

    amount = _amount_string(original_price)
    if amount is None:
        return None
    return {"amount": amount, "currency": currency, "unit": "hour"}


def _clean_cached_price_map(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, dict[str, str]] = {}
    for raw_region, raw_price in value.items():
        region = str(raw_region or "").strip()
        if not region or not isinstance(raw_price, dict):
            continue
        amount = _amount_string(raw_price.get("amount"))
        currency = str(raw_price.get("currency") or "").strip().upper()
        unit = str(raw_price.get("unit") or "").strip().lower()
        if amount is None or currency not in {"CNY", "USD"} or unit != "hour":
            continue
        cleaned[region] = {
            "amount": amount,
            "currency": currency,
            "unit": "hour",
        }
    return cleaned


def _load_cached_prices(path: Path | None = None) -> dict[str, dict[str, dict[str, str]]]:
    if path is None:
        configured = os.environ.get(PREVIOUS_CATALOG_ENV)
        path = Path(configured) if configured else DEFAULT_PREVIOUS_CATALOG
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            catalog = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

    try:
        instances = catalog["providers"]["alibaba"]["instances"]
    except (KeyError, TypeError):
        return {}
    if not isinstance(instances, list):
        return {}

    cached: dict[str, dict[str, dict[str, str]]] = {}
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        instance_type = str(instance.get("instanceType") or "").strip()
        prices = _clean_cached_price_map(instance.get("onDemandPrices"))
        if instance_type and prices:
            cached[instance_type] = prices
    return cached


def _rotate_daily(
    values: list[tuple[str, str]],
    *,
    day_ordinal: int,
) -> list[tuple[str, str]]:
    if not values:
        return []
    # A relatively-prime stride changes the head substantially each day. This
    # prevents a slow or throttled run from pricing the same fixed prefix forever.
    offset = (day_ordinal * 257) % len(values)
    return values[offset:] + values[:offset]


def _fetch_on_demand_prices(
    access_key_id: str,
    access_key_secret: str,
    availability: dict[str, dict[str, set[str]]],
    *,
    cached_prices: dict[str, dict[str, dict[str, str]]] | None = None,
    time_budget_seconds: float = PRICE_TIME_BUDGET_SECONDS,
    queries_per_second: float = PRICE_QUERIES_PER_SECOND,
    workers: int = PRICE_WORKERS,
    day_ordinal: int | None = None,
) -> dict[str, dict[str, dict[str, str]]]:
    """Fetch one real regional Linux hourly price per available instance type.

    DescribePrice has no batch form, so calls are rate-limited and bounded by a
    provider-local deadline. Valid prior quotes are retained; entirely unpriced
    types run first, then unquoted regions, and each group rotates daily so
    partial runs make progress without copying one region's price to another.
    """

    cached_prices = cached_prices or {}
    result: dict[str, dict[str, dict[str, str]]] = {}
    missing: list[tuple[str, str]] = []
    expand: list[tuple[str, str]] = []
    refresh: list[tuple[str, str]] = []

    if day_ordinal is None:
        day_ordinal = datetime.now(timezone.utc).date().toordinal()

    for instance_type in sorted(availability):
        regions = sorted(availability[instance_type].get("regions", set()))
        if not regions:
            continue
        available_regions = set(regions)
        retained = {
            region: price
            for region, price in _clean_cached_price_map(
                cached_prices.get(instance_type)
            ).items()
            if region in available_regions
        }
        if retained:
            result[instance_type] = retained
            unpriced_regions = sorted(available_regions - set(retained))
            if unpriced_regions:
                expand.append((instance_type, unpriced_regions[0]))
            else:
                retained_regions = sorted(retained)
                refresh.append(
                    (
                        instance_type,
                        retained_regions[day_ordinal % len(retained_regions)],
                    )
                )
        else:
            missing.append((instance_type, regions[0]))

    queue = _rotate_daily(missing, day_ordinal=day_ordinal)
    queue.extend(_rotate_daily(expand, day_ordinal=day_ordinal))
    queue.extend(_rotate_daily(refresh, day_ordinal=day_ordinal))
    if not queue or time_budget_seconds <= 0 or queries_per_second <= 0 or workers <= 0:
        return result

    deadline = time.monotonic() + time_budget_seconds
    interval = 1 / queries_per_second
    rate_lock = threading.Lock()
    next_slot = [time.monotonic()]
    thread_clients = threading.local()

    def price_client(region_id: str) -> Any:
        clients = getattr(thread_clients, "by_region", None)
        if clients is None:
            clients = {}
            thread_clients.by_region = clients
        client = clients.get(region_id)
        if client is None:
            client = _make_price_client(
                access_key_id,
                access_key_secret,
                region_id,
            )
            clients[region_id] = client
        return client

    def query(item: tuple[str, str]) -> tuple[str, str, dict[str, str] | None, bool]:
        instance_type, region_id = item
        if time.monotonic() >= deadline:
            return instance_type, region_id, None, False
        with rate_lock:
            now = time.monotonic()
            if now >= deadline:
                return instance_type, region_id, None, False
            slot = max(now, next_slot[0])
            next_slot[0] = slot + interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, max(0, deadline - time.monotonic())))
        if time.monotonic() >= deadline:
            return instance_type, region_id, None, False
        try:
            payload = _invoke(
                price_client(region_id),
                "DescribePrice",
                RegionId=region_id,
                ResourceType="instance",
                InstanceType=instance_type,
                PriceUnit="Hour",
                Period=1,
                InstanceNetworkType="vpc",
                InternetChargeType="PayByTraffic",
                InternetMaxBandwidthOut=0,
                SpotStrategy="NoSpot",
            )
            return instance_type, region_id, _extract_on_demand_price(payload), True
        except Exception:
            # Pricing is optional enrichment. Inventory remains publishable when
            # a retired SKU has no price or the pricing endpoint is throttled.
            return instance_type, region_id, None, True

    attempted = 0
    refreshed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(query, item) for item in queue]
        for future in as_completed(futures):
            instance_type, region_id, price, did_attempt = future.result()
            attempted += int(did_attempt)
            if price is None:
                continue
            result.setdefault(instance_type, {})[region_id] = price
            refreshed += 1

    print(
        f"alibaba: {refreshed}/{attempted} DescribePrice calls returned "
        f"Linux pay-as-you-go hourly prices; {len(result)}/{len(queue)} "
        "available instance types have a cached or current price",
        flush=True,
    )
    return result


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
    on_demand_prices = _fetch_on_demand_prices(
        access_key_id,
        access_key_secret,
        available,
        cached_prices=_load_cached_prices(),
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
                "onDemandPrices": on_demand_prices.get(instance_type, {}),
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
