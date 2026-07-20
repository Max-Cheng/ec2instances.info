# China cloud instance catalogs

The Alibaba Cloud, Tencent Cloud, Volcengine, and Huawei Cloud pages are built
from the providers' read-only instance catalog APIs. The ingestion job follows
all pagination, enumerates regions and availability zones, merges availability
by instance type, and writes `next/data/regionalClouds.generated.json` before
writing the public `/data/china-clouds.json` snapshot. The pages load the public
snapshot at runtime, while the checked-in TypeScript catalog remains a small
fallback for local builds, initial rendering, and failed client refreshes.

Where an official API exposes it, the snapshot also stores the public Linux
pay-as-you-go price for one instance-hour, keyed by the exact region that was
quoted. The table shows the selected region's price; the all-regions view shows
the lowest collected quote and labels it `From`. Prices remain in the native
currency returned by the provider instead of applying an unverified exchange
rate. Account discounts, disks,
bandwidth, images, taxes, Reserved/Spot prices, and prepaid terms are excluded.
When an API does not return a usable numeric quote for a type and region, the
cell links to the provider's official calculator instead of inventing or
copying a price from another region.

The pages reuse the main site's virtualized comparison table, column filters,
sorting, selection, comparison, export, and search controls. AWS-only
Reserved/Spot, ECU, EBS, and benchmark controls are omitted because the China
cloud APIs do not expose equivalent data with a common definition.

## Data sources

- Alibaba Cloud ECS:
  `DescribeRegions`, `DescribeZones`, `DescribeInstanceTypes`, and
  `DescribeAvailableResource`; `DescribePrice` supplies bounded, rotating
  Linux pay-as-you-go quotes because it accepts only one instance type per call
- Tencent Cloud CVM:
  `DescribeRegions`, `DescribeZones`, `DescribeInstanceTypeConfigs`, and
  `DescribeZoneInstanceConfigInfos` (including its public hourly `UnitPrice`)
- Volcengine ECS:
  `DescribeRegions`, `DescribeZones`, `DescribeInstanceTypes`, and
  `DescribeAvailableResource`. Billing `QueryPriceForPayAsYouGo` requires
  internal product, configuration, and charge-item codes that the ECS catalog
  does not expose, so Volcengine currently retains the official calculator
  fallback.
- Huawei Cloud ECS:
  IAM `KeystoneListRegions` and `KeystoneListAuthProjects`, plus ECS
  `ListServerAzInfo` and paginated `ListFlavors`; BSS
  `ListOnDemandResourceRatings` supplies `official_website_amount` in batches

The availability columns are a point-in-time view of standard, non-spot
purchase availability. They do not claim that a flavor is available under
every billing term or to every account. The total shown on each page is the
number of unique instance type IDs returned by the specification APIs; a type
with no currently reported standard purchase availability remains in the
catalog with zero covered regions and zones.

## Updating the catalogs

The fork's `Daily GitHub Pages` workflow runs daily at 02:23 Asia/Shanghai and
can also be started manually. Provider calls run concurrently. Pushes to
`main` perform the full Node verification and static build once, then cache the
validated Pages shell by frontend content. Scheduled and manual runs restore
that shell, refresh only the Python/API data, and overlay the normalized
snapshot at `/data/china-clouds.json`. A cache miss safely falls back to
rebuilding the shell, but daily refreshes normally skip Node installation,
tests, and Next.js. Every event first tries to validate and reuse the deployed
catalog, so bounded Alibaba price coverage accumulates instead of resetting on
pushes. The provider refresh has a three-minute hard deadline and the complete
job has a fifteen-minute ceiling. If a provider SDK or network path stalls,
the workflow records a warning and publishes completed, validated provider
checkpoints while unfinished providers retain their previous snapshot. A first
push with no previous snapshot still fails on timeout. If nothing changed, a
scheduled or manual run skips the redundant Pages deployment. Every run still
fails on explicit provider, authentication, schema, or catalog-validation
errors. Starting a newer run also cancels an older in-progress run.

To run the ingestion locally:

```bash
python -m pip install --requirement scripts/china_cloud/requirements.txt
python -m scripts.update_china_clouds
```

The command expects these environment variables:

```text
ALIBABA_CLOUD_ACCESS_KEY_ID
ALIBABA_CLOUD_ACCESS_KEY_SECRET
TENCENTCLOUD_SECRET_ID
TENCENTCLOUD_SECRET_KEY
VOLCENGINE_ACCESS_KEY_ID
VOLCENGINE_SECRET_ACCESS_KEY
HUAWEI_ACCESS_KEY_ID
HUAWEI_SECRET_ACCESS_KEY
```

Use read-only subaccounts. The scraper never creates, modifies, starts, or
deletes cloud resources, and it does not print credentials or signed requests.
The keys must be allowed to call the APIs listed above. Alibaba Cloud pricing
requires `ecs:DescribePrice` on resource `*`. Tencent Cloud pricing is already
included in `cvm:DescribeZoneInstanceConfigInfos`; that action must also allow
resource `*`. Huawei's public website rating call uses the same AK/SK; an IAM
user needs the read-only `billing:contract:viewDiscount` permission, but no
order or purchase permission. In particular, Huawei Cloud still
requires `ecs:cloudServerFlavors:get` for flavors and
`ecs:cloudServers:listServersDetails` for availability zones; the update fails
instead of publishing incomplete AZ coverage when either call is denied.
If Huawei IAM lists a region that the collector account has not opened, the
exact `APIGW.0802` response is reported in `skippedRegions`; other permission
errors still fail the update. Do not grant instance creation, order, payment,
or trade permissions to this read-only collector.

The validation test in `next/utils/regionalClouds.test.ts` checks minimum
coverage, unique identifiers, positive CPU/memory values, price shape and
region attribution, and official source hosts. Python unit tests cover
pagination parsing, availability and price merging, and normalization. The
refresh also requires at least one numeric quote from Alibaba, Tencent, and
Huawei before publishing. If a provider API fails or returns an implausibly
small catalog, the Pages workflow fails and the previously deployed site
remains online.
