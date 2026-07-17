#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


PROVIDER_SLUGS = ("alibaba", "tencent", "volcengine", "huawei")
MINIMUM_INSTANCE_COUNTS = {
    # Conservative floors based on the first complete production snapshot.
    # These are deliberately below normal counts but above one-page/smoke data.
    "alibaba": 1000,
    "tencent": 300,
    "volcengine": 150,
    "huawei": 100,
}
SECRET_NAMES = (
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "TENCENTCLOUD_SECRET_ID",
    "TENCENTCLOUD_SECRET_KEY",
    "VOLCENGINE_ACCESS_KEY_ID",
    "VOLCENGINE_SECRET_ACCESS_KEY",
    "HUAWEI_ACCESS_KEY_ID",
    "HUAWEI_SECRET_ACCESS_KEY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch complete read-only instance catalogs from China cloud APIs."
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=PROVIDER_SLUGS,
        dest="providers",
        help="Fetch only one provider (repeatable). Defaults to all providers.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("next/data/regionalClouds.generated.json"),
    )
    parser.add_argument(
        "--public-output",
        type=Path,
        default=Path("next/public/data/china-clouds.json"),
    )
    return parser.parse_args()


def redact(error: Exception) -> str:
    message = " ".join(str(error).split())
    for name in SECRET_NAMES:
        value = os.environ.get(name)
        if value:
            message = message.replace(value, "***")
    return message[:1000] or error.__class__.__name__


def validate_provider(slug: str, provider: dict[str, Any]) -> None:
    if provider.get("slug") != slug:
        raise ValueError(f"{slug}: provider slug mismatch")
    instances = provider.get("instances")
    if not isinstance(instances, list):
        raise ValueError(f"{slug}: instances must be a list")
    minimum = MINIMUM_INSTANCE_COUNTS[slug]
    if len(instances) < minimum:
        raise ValueError(
            f"{slug}: only {len(instances)} unique instance types; expected at least {minimum}"
        )

    region_count = int(provider.get("regionCount") or 0)
    zone_count = int(provider.get("zoneCount") or 0)
    if region_count <= 0:
        raise ValueError(f"{slug}: no regions were discovered")
    if zone_count <= 0:
        raise ValueError(f"{slug}: no availability zones were discovered")

    skipped_regions = provider.get("skippedRegions", [])
    if not isinstance(skipped_regions, list) or any(
        not isinstance(region, str) or not region.strip()
        for region in skipped_regions
    ):
        raise ValueError(f"{slug}: skippedRegions must be a list of region IDs")
    if len(set(skipped_regions)) != len(skipped_regions):
        raise ValueError(f"{slug}: skippedRegions contains duplicates")

    seen: set[str] = set()
    instances_with_availability = 0
    for instance in instances:
        instance_type = str(instance.get("instanceType") or "")
        if not instance_type or instance_type in seen:
            raise ValueError(f"{slug}: blank or duplicate instance type {instance_type!r}")
        seen.add(instance_type)
        if float(instance.get("vCPU") or 0) <= 0:
            raise ValueError(f"{slug}/{instance_type}: vCPU must be positive")
        if float(instance.get("memoryGiB") or 0) <= 0:
            raise ValueError(f"{slug}/{instance_type}: memoryGiB must be positive")
        source_url = str(instance.get("sourceUrl") or "")
        if not source_url.startswith("https://"):
            raise ValueError(f"{slug}/{instance_type}: invalid sourceUrl")
        regions = instance.get("regions")
        zones = instance.get("zones")
        if not isinstance(regions, list) or not isinstance(zones, list):
            raise ValueError(f"{slug}/{instance_type}: regions and zones must be lists")
        if int(instance.get("availableRegionCount") or 0) != len(regions):
            raise ValueError(f"{slug}/{instance_type}: region count mismatch")
        if int(instance.get("availableZoneCount") or 0) != len(zones):
            raise ValueError(f"{slug}/{instance_type}: zone count mismatch")
        if regions and zones:
            instances_with_availability += 1

    if instances_with_availability == 0:
        raise ValueError(f"{slug}: no instance type has regional/AZ availability")


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(serialized)
        temporary = Path(handle.name)
    temporary.replace(path)


def write_step_summary(catalog: dict[str, Any]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        "## China cloud catalog refresh",
        "",
        "| Provider | Unique instance types | Regions | Zones | Skipped regions |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for slug in PROVIDER_SLUGS:
        provider = catalog["providers"].get(slug)
        if not provider:
            continue
        lines.append(
            f"| {slug} | {len(provider['instances'])} | "
            f"{provider['regionCount']} | {provider['zoneCount']} | "
            f"{len(provider.get('skippedRegions', []))} |"
        )
    lines.append("")
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def fetch_provider(slug: str) -> dict[str, Any]:
    print(f"{slug}: fetching full catalog", flush=True)
    module = importlib.import_module(f"scripts.china_cloud.providers.{slug}")
    provider = module.fetch()
    validate_provider(slug, provider)
    print(
        f"{slug}: {len(provider['instances'])} unique instance types, "
        f"{provider['regionCount']} regions, {provider['zoneCount']} zones",
        flush=True,
    )
    return provider


def main() -> int:
    args = parse_args()
    selected = tuple(args.providers or PROVIDER_SLUGS)
    fetched: dict[str, Any] = {}

    # Each provider has independent credentials, endpoints, and rate limits.
    # Fetch them concurrently so the daily job takes roughly as long as the
    # slowest cloud instead of the sum of all four clouds.
    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        futures = {
            executor.submit(fetch_provider, slug): slug for slug in selected
        }
        failed = False
        for future in as_completed(futures):
            slug = futures[future]
            try:
                fetched[slug] = future.result()
            except Exception as error:
                failed = True
                print(
                    f"::error title={slug} catalog refresh failed::"
                    f"{error.__class__.__name__}: {redact(error)}",
                    file=sys.stderr,
                    flush=True,
                )

    if failed:
        return 1

    # Preserve the requested provider order in both JSON and summaries even
    # though concurrent requests complete in a nondeterministic order.
    providers = {slug: fetched[slug] for slug in selected}

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    catalog = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "providers": providers,
        "totals": {
            "providers": len(providers),
            "uniqueInstanceTypes": sum(
                len(provider["instances"]) for provider in providers.values()
            ),
        },
    }
    atomic_write(args.output, catalog)
    atomic_write(args.public_output, catalog)
    write_step_summary(catalog)
    print(
        f"wrote {catalog['totals']['uniqueInstanceTypes']} unique instance types "
        f"to {args.output} and {args.public_output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
