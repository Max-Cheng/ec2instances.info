from __future__ import annotations

import os
import re
from collections.abc import Iterable
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

        current = merged.get(instance_type)
        if current is None:
            merged[instance_type] = record
            continue

        current["regions"] = sorted(set(current["regions"]) | set(record["regions"]))
        current["zones"] = sorted(set(current["zones"]) | set(record["zones"]))
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
