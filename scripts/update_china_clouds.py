#!/usr/bin/env python3
from __future__ import annotations

import argparse
import faulthandler
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

from scripts.china_cloud.common import normalize_on_demand_prices


PROVIDER_SLUGS = ("alibaba", "tencent", "volcengine", "huawei")
PRICE_PROVIDER_SLUGS = {"alibaba", "tencent", "huawei"}
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
    parser.add_argument(
        "--previous",
        type=Path,
        help="Validated previous full catalog used to checkpoint partial progress.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="Atomically updated full catalog checkpoint for timeout recovery.",
    )
    parser.add_argument(
        "--failure-marker",
        type=Path,
        help="Touched when a provider raises an explicit error.",
    )
    parser.add_argument(
        "--completion-marker",
        type=Path,
        help=(
            "Append each provider slug after its validated checkpoint is written. "
            "The caller owns marker lifecycle across retries."
        ),
    )
    parser.add_argument(
        "--validate-only",
        type=Path,
        help="Validate an existing full catalog and exit without calling providers.",
    )
    return parser.parse_args()


def redact(error: Exception) -> str:
    message = " ".join(str(error).split())
    for name in SECRET_NAMES:
        value = os.environ.get(name)
        if value:
            message = message.replace(value, "***")
    return message[:1000] or error.__class__.__name__


def validate_provider(
    slug: str,
    provider: dict[str, Any],
    *,
    require_prices: bool = False,
) -> None:
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
    priced_instances = 0
    price_currencies: set[str] = set()
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

        prices = instance.get("onDemandPrices")
        if prices is not None:
            if not isinstance(prices, dict) or not prices:
                raise ValueError(
                    f"{slug}/{instance_type}: onDemandPrices must be a non-empty object"
                )
            if normalize_on_demand_prices(prices) != prices:
                raise ValueError(
                    f"{slug}/{instance_type}: invalid on-demand price data"
                )
            unknown_price_regions = set(prices) - set(regions)
            if unknown_price_regions:
                raise ValueError(
                    f"{slug}/{instance_type}: price regions are not in availability: "
                    f"{sorted(unknown_price_regions)}"
                )
            price_currencies.update(
                str(price["currency"]) for price in prices.values()
            )
            priced_instances += 1

    if instances_with_availability == 0:
        raise ValueError(f"{slug}: no instance type has regional/AZ availability")
    if require_prices and slug in PRICE_PROVIDER_SLUGS and priced_instances == 0:
        raise ValueError(f"{slug}: no public Linux on-demand prices were returned")
    if len(price_currencies) > 1:
        raise ValueError(
            f"{slug}: mixed price currencies are not comparable: "
            f"{sorted(price_currencies)}"
        )


def build_catalog(
    providers: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    ordered = {
        slug: providers[slug]
        for slug in PROVIDER_SLUGS
        if slug in providers
    }
    has_required_prices = all(
        any(
            instance.get("onDemandPrices")
            for instance in ordered.get(slug, {}).get("instances", [])
        )
        for slug in PRICE_PROVIDER_SLUGS
    )
    return {
        # Version 1 remains readable during the first rolling deployment, when
        # unfinished providers can still come from the legacy no-price snapshot.
        "schemaVersion": 2 if has_required_prices else 1,
        "generatedAt": generated_at,
        "providers": ordered,
        "totals": {
            "providers": len(ordered),
            "uniqueInstanceTypes": sum(
                len(provider["instances"]) for provider in ordered.values()
            ),
        },
    }


def validate_catalog(catalog: dict[str, Any]) -> None:
    schema_version = catalog.get("schemaVersion")
    if schema_version not in {1, 2}:
        raise ValueError("catalog: schemaVersion must be 1 or 2")
    generated_at = catalog.get("generatedAt")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise ValueError("catalog: generatedAt must be a non-empty string")

    providers = catalog.get("providers")
    if not isinstance(providers, dict):
        raise ValueError("catalog: providers must be an object")
    if set(providers) != set(PROVIDER_SLUGS):
        raise ValueError("catalog: all four providers must be present")
    for slug in PROVIDER_SLUGS:
        provider = providers.get(slug)
        if not isinstance(provider, dict):
            raise ValueError(f"catalog: {slug} provider must be an object")
        validate_provider(slug, provider, require_prices=schema_version >= 2)

    totals = catalog.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("catalog: totals must be an object")
    if int(totals.get("providers") or 0) != len(PROVIDER_SLUGS):
        raise ValueError("catalog: provider total mismatch")
    expected_instances = sum(
        len(providers[slug]["instances"]) for slug in PROVIDER_SLUGS
    )
    if int(totals.get("uniqueInstanceTypes") or 0) != expected_instances:
        raise ValueError("catalog: instance total mismatch")


def load_catalog(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict):
        raise ValueError(f"{path}: catalog must be an object")
    validate_catalog(catalog)
    return catalog


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(serialized)
        temporary = Path(handle.name)
    temporary.replace(path)


def record_provider_completion(path: Path, slug: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{slug}\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_step_summary(catalog: dict[str, Any]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        "## China cloud catalog refresh",
        "",
        "| Provider | Unique instance types | Priced types | Regions | Zones | Skipped regions |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for slug in PROVIDER_SLUGS:
        provider = catalog["providers"].get(slug)
        if not provider:
            continue
        lines.append(
            f"| {slug} | {len(provider['instances'])} | "
            f"{sum(bool(instance.get('onDemandPrices')) for instance in provider['instances'])} | "
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
    validate_provider(slug, provider, require_prices=True)
    print(
        f"{slug}: {len(provider['instances'])} unique instance types, "
        f"{sum(bool(instance.get('onDemandPrices')) for instance in provider['instances'])} priced, "
        f"{provider['regionCount']} regions, {provider['zoneCount']} zones",
        flush=True,
    )
    return provider


def fetch_provider_guarded(
    slug: str,
    failure_marker: Path | None,
) -> dict[str, Any]:
    try:
        return fetch_provider(slug)
    except Exception:
        # Write from the worker before propagating the error, closing the small
        # window where the outer timeout could kill the coordinator before it
        # records that this was an explicit provider failure rather than a hang.
        if failure_marker:
            failure_marker.parent.mkdir(parents=True, exist_ok=True)
            failure_marker.touch()
        raise


def main() -> int:
    args = parse_args()
    if args.validate_only:
        catalog = load_catalog(args.validate_only)
        print(
            f"validated {catalog['totals']['uniqueInstanceTypes']} unique instance "
            f"types in {args.validate_only}",
            flush=True,
        )
        return 0

    if args.completion_marker and not args.checkpoint:
        raise ValueError("--completion-marker requires --checkpoint")

    selected = tuple(args.providers or PROVIDER_SLUGS)
    fetched: dict[str, Any] = {}
    previous = load_catalog(args.previous) if args.previous else None
    if args.previous:
        os.environ["CHINA_CLOUD_PREVIOUS_CATALOG"] = str(args.previous)
    providers: dict[str, Any] = dict(previous["providers"]) if previous else {}
    checkpoint_generated_at = str(previous["generatedAt"]) if previous else ""

    if args.failure_marker and args.failure_marker.exists():
        args.failure_marker.unlink()
    if args.checkpoint and previous:
        atomic_write(
            args.checkpoint,
            build_catalog(providers, checkpoint_generated_at),
        )

    stack_dump_seconds = float(
        os.environ.get("CHINA_CLOUD_STACK_DUMP_SECONDS", "0") or 0
    )
    stack_dumps_enabled = stack_dump_seconds > 0
    if stack_dumps_enabled:
        print(
            f"transport diagnostics: dumping all Python thread stacks every "
            f"{stack_dump_seconds:g}s while providers run",
            flush=True,
        )
        faulthandler.dump_traceback_later(
            stack_dump_seconds,
            repeat=True,
            file=sys.stderr,
        )

    failed = False
    try:
        # Each provider has independent credentials, endpoints, and rate limits.
        # Fetch them concurrently so the daily job takes roughly as long as the
        # slowest cloud instead of the sum of all four clouds.
        with ThreadPoolExecutor(max_workers=len(selected)) as executor:
            futures = {
                executor.submit(
                    fetch_provider_guarded, slug, args.failure_marker
                ): slug
                for slug in selected
            }
            for future in as_completed(futures):
                slug = futures[future]
                try:
                    fetched[slug] = future.result()
                    providers[slug] = fetched[slug]
                    if args.checkpoint and previous:
                        atomic_write(
                            args.checkpoint,
                            build_catalog(providers, checkpoint_generated_at),
                        )
                        if args.completion_marker:
                            record_provider_completion(args.completion_marker, slug)
                except Exception as error:
                    failed = True
                    print(
                        f"::error title={slug} catalog refresh failed::"
                        f"{error.__class__.__name__}: {redact(error)}",
                        file=sys.stderr,
                        flush=True,
                    )
    finally:
        if stack_dumps_enabled:
            faulthandler.cancel_dump_traceback_later()

    if failed:
        return 1

    # Preserve the requested provider order in both JSON and summaries even
    # though concurrent requests complete in a nondeterministic order.
    if not previous:
        providers = {slug: fetched[slug] for slug in selected}

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    catalog = build_catalog(providers, generated_at)
    if args.checkpoint:
        atomic_write(args.checkpoint, catalog)
        if args.completion_marker and not previous:
            for slug in selected:
                record_provider_completion(args.completion_marker, slug)
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
