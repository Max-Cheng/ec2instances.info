from __future__ import annotations

import os
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


CATEGORIES = {
    "General purpose",
    "Compute optimized",
    "Memory optimized",
    "Accelerated computing",
    "Storage optimized",
    "High performance computing",
    "Bare metal",
    "Other",
}

ARCHITECTURES = {"x86_64", "arm64", "unknown"}

EMPTY_TEXT = {"", "unknown", "varies by instance type", "not published"}

PRICE_CURRENCIES = {"CNY", "USD"}
ONE_YEAR_HOURS = Decimal(365 * 24)
EFFECTIVE_HOURLY_QUANTUM = Decimal("0.00000001")


def log_progress(
    provider: str,
    stage: str,
    status: str,
    **details: Any,
) -> None:
    """Emit a compact, provider-scoped progress line for CI diagnostics."""

    suffix = " ".join(
        f"{key}={str(value).replace(' ', '_')}"
        for key, value in sorted(details.items())
    )
    print(
        f"{provider}: stage={stage} status={status}"
        + (f" {suffix}" if suffix else ""),
        flush=True,
    )


def require_env(*names: str) -> tuple[str, ...]:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"missing GitHub Secret(s): {', '.join(missing)}")
    return tuple(os.environ[name] for name in names)


def number(value: Any, default: float = 0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group()) if match else default


def integer(value: Any, default: int = 0) -> int:
    return int(number(value, default))


def format_packet_rate(pps: Any) -> str:
    """Format a packet rate supplied as packets per second."""

    rate = number(pps)
    if rate <= 0:
        return ""
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:g} Mpps"
    if rate >= 1_000:
        return f"{rate / 1_000:g} Kpps"
    return f"{rate:g} pps"


def nonempty(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


def normalize_architecture(value: Any, instance_type: str = "") -> str:
    text = f"{value or ''} {instance_type}".lower()
    if any(token in text for token in ("arm", "aarch64", "kunpeng", "yitian")):
        return "arm64"
    if any(token in text for token in ("x86", "amd64", "intel", "amd", "epyc", "xeon")):
        return "x86_64"
    return "unknown"


def classify_category(
    family: str,
    instance_type: str,
    vcpu: float,
    memory_gib: float,
    *,
    gpu_count: float = 0,
    hint: str = "",
) -> str:
    text = f"{family} {instance_type} {hint}".lower()
    compact_family = re.sub(r"[^a-z0-9]", "", family.lower())
    if any(token in text for token in ("bare metal", "baremetal", "physical")) or compact_family.startswith(("ebm", "bms")):
        return "Bare metal"
    if gpu_count > 0 or any(
        token in text
        for token in (
            " gpu",
            "gpu ",
            "accelerated",
            "inference",
            "training",
            "fpga",
            "npu",
        )
    ) or compact_family.startswith(("gn", "ga", "vg", "pi", "pni", "gpu")):
        return "Accelerated computing"
    if any(token in text for token in ("high performance", "hpc")) or compact_family.startswith(("hfc", "hfg", "hfr", "ehpc")):
        return "High performance computing"
    if any(token in text for token in ("local ssd", "local disk", "storage optimized")) or compact_family.startswith(("i", "d", "is", "im")):
        return "Storage optimized"
    ratio = memory_gib / vcpu if vcpu else 0
    if any(token in hint.lower() for token in ("memory", "large memory")) or compact_family.startswith(("m", "r", "re")) or ratio >= 6:
        return "Memory optimized"
    if "compute" in hint.lower() or compact_family.startswith(("c", "hc")) or (0 < ratio <= 2.5):
        return "Compute optimized"
    if vcpu > 0 and memory_gib > 0:
        return "General purpose"
    return "Other"


def family_from_instance_type(instance_type: str) -> str:
    value = instance_type.strip()
    if value.startswith("ecs."):
        parts = value.split(".")
        return parts[1] if len(parts) > 2 else value
    if "." in value:
        return value.split(".", 1)[0]
    if "_" in value:
        return value.split("_", 1)[0]
    match = re.match(r"([a-zA-Z]+\d*[a-zA-Z]*)", value)
    return match.group(1) if match else value


def _normalize_hourly_price(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None

    currency = str(value.get("currency") or "").upper().strip()
    unit = str(value.get("unit") or "").lower().strip()
    try:
        amount = Decimal(str(value.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if (
        not amount.is_finite()
        or amount <= 0
        or currency not in PRICE_CURRENCIES
        or unit != "hour"
    ):
        return None
    return {
        "amount": format(amount.normalize(), "f"),
        "currency": currency,
        "unit": "hour",
    }


def normalize_on_demand_prices(value: Any) -> dict[str, dict[str, str]]:
    """Normalize positive per-instance hourly prices keyed by real region ID."""

    if not isinstance(value, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for raw_region, raw_price in value.items():
        region = str(raw_region or "").strip()
        if not region or not isinstance(raw_price, dict):
            continue

        price = _normalize_hourly_price(raw_price)
        if price:
            normalized[region] = price
    return dict(sorted(normalized.items()))


def normalize_subscription_prices(value: Any) -> dict[str, dict[str, str]]:
    """Normalize public one-year all-upfront prices and effective hourly cost."""

    if not isinstance(value, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for raw_region, raw_price in value.items():
        region = str(raw_region or "").strip()
        price = _normalize_hourly_price(raw_price)
        if not region or not price or not isinstance(raw_price, dict):
            continue
        try:
            total_amount = Decimal(str(raw_price.get("totalAmount")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if (
            not total_amount.is_finite()
            or total_amount <= 0
            or str(raw_price.get("term") or "").strip() != "1-year"
            or str(raw_price.get("payment") or "").strip() != "all-upfront"
        ):
            continue
        effective_hourly = (total_amount / ONE_YEAR_HOURS).quantize(
            EFFECTIVE_HOURLY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        actual_hourly = Decimal(price["amount"]).quantize(
            EFFECTIVE_HOURLY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if actual_hourly != effective_hourly:
            continue
        normalized[region] = {
            **price,
            "amount": format(effective_hourly.normalize(), "f"),
            "totalAmount": format(total_amount.normalize(), "f"),
            "term": "1-year",
            "payment": "all-upfront",
        }
    return dict(sorted(normalized.items()))


def _normalize_utc_timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_spot_prices(value: Any) -> dict[str, dict[str, str]]:
    """Normalize current public spot prices, optionally retaining quote metadata."""

    if not isinstance(value, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for raw_region, raw_price in value.items():
        region = str(raw_region or "").strip()
        price = _normalize_hourly_price(raw_price)
        if not region or not price or not isinstance(raw_price, dict):
            continue
        raw_observed_at = str(raw_price.get("observedAt") or "").strip()
        observed_at = _normalize_utc_timestamp(raw_observed_at)
        zone = str(raw_price.get("zone") or "").strip()
        if raw_observed_at and observed_at is None:
            continue
        if observed_at:
            price["observedAt"] = observed_at
        if zone:
            price["zone"] = zone
        normalized[region] = price
    return dict(sorted(normalized.items()))


def merge_instances(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in records:
        instance_type = str(raw.get("instanceType") or "").strip()
        vcpu = number(raw.get("vCPU"))
        memory_gib = number(raw.get("memoryGiB"))
        if not instance_type or vcpu <= 0 or memory_gib <= 0:
            continue

        family = nonempty(raw.get("family"), family_from_instance_type(instance_type))
        architecture = normalize_architecture(raw.get("architecture"), instance_type)
        category = str(raw.get("category") or "")
        if category not in CATEGORIES:
            category = classify_category(
                family,
                instance_type,
                vcpu,
                memory_gib,
                gpu_count=number(raw.get("gpuCount")),
                hint=str(raw.get("categoryHint") or ""),
            )

        record = {
            "instanceType": instance_type,
            "family": family,
            "familyName": nonempty(raw.get("familyName"), family),
            "category": category,
            "vCPU": int(vcpu) if vcpu.is_integer() else vcpu,
            "memoryGiB": int(memory_gib) if memory_gib.is_integer() else round(memory_gib, 4),
            "architecture": architecture,
            "processor": nonempty(raw.get("processor"), "Provider-managed CPU"),
            "networkPerformance": nonempty(raw.get("networkPerformance"), "Not published"),
            "localStorage": nonempty(raw.get("localStorage"), "Cloud disks"),
            "sourceUrl": nonempty(raw.get("sourceUrl"), "#"),
            "regions": sorted({str(item) for item in raw.get("regions", []) if item}),
            "zones": sorted({str(item) for item in raw.get("zones", []) if item}),
        }
        for field, normalizer in (
            ("onDemandPrices", normalize_on_demand_prices),
            ("subscriptionPrices", normalize_subscription_prices),
            ("spotPrices", normalize_spot_prices),
        ):
            prices = normalizer(raw.get(field))
            if prices:
                record[field] = prices

        current = merged.get(instance_type)
        if current is None:
            merged[instance_type] = record
            continue

        current["regions"] = sorted(set(current["regions"]) | set(record["regions"]))
        current["zones"] = sorted(set(current["zones"]) | set(record["zones"]))
        for field in ("onDemandPrices", "subscriptionPrices", "spotPrices"):
            current_prices = current.setdefault(field, {})
            for region, price in record.get(field, {}).items():
                existing = current_prices.get(region)
                if existing is None:
                    current_prices[region] = price
                    continue
                if existing["currency"] == price["currency"] and Decimal(
                    price["amount"]
                ) < Decimal(existing["amount"]):
                    current_prices[region] = price
            if not current_prices:
                current.pop(field, None)
        for key in (
            "family",
            "familyName",
            "processor",
            "networkPerformance",
            "localStorage",
            "sourceUrl",
        ):
            if str(current[key]).strip().lower() in EMPTY_TEXT and str(record[key]).strip().lower() not in EMPTY_TEXT:
                current[key] = record[key]
        if current["architecture"] == "unknown" and record["architecture"] != "unknown":
            current["architecture"] = record["architecture"]

    for record in merged.values():
        record["availableRegionCount"] = len(record["regions"])
        record["availableZoneCount"] = len(record["zones"])
    return sorted(merged.values(), key=lambda item: natural_key(item["instanceType"]))


def natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def provider_result(
    slug: str,
    records: Iterable[dict[str, Any]],
    regions: Iterable[str],
    zones: Iterable[str],
) -> dict[str, Any]:
    instances = merge_instances(records)
    return {
        "slug": slug,
        "regionCount": len(set(regions)),
        "zoneCount": len(set(zones)),
        "instances": instances,
    }
