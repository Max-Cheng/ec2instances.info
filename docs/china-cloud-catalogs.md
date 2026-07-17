# China cloud instance catalogs

The Alibaba Cloud, Tencent Cloud, Volcengine, and Huawei Cloud pages are built
from the providers' read-only instance catalog APIs. The ingestion job follows
all pagination, enumerates regions and availability zones, merges availability
by instance type, and writes `next/data/regionalClouds.generated.json` before
the Next.js build. The checked-in TypeScript catalog remains a small fallback
for local and pull-request builds that do not have cloud credentials.

These pages intentionally do not copy prices into the repository. Prices vary
by region, operating system, billing term, sales channel, and account-level
discount, so each page links to the provider's official price calculator.

## Data sources

- Alibaba Cloud ECS:
  `DescribeRegions`, `DescribeZones`, `DescribeInstanceTypes`, and
  `DescribeAvailableResource`
- Tencent Cloud CVM:
  `DescribeRegions`, `DescribeZones`, `DescribeInstanceTypeConfigs`, and
  `DescribeZoneInstanceConfigInfos`
- Volcengine ECS:
  `DescribeRegions`, `DescribeZones`, `DescribeInstanceTypes`, and
  `DescribeAvailableResource`
- Huawei Cloud ECS:
  IAM `KeystoneListRegions` and `KeystoneListAuthProjects`, plus ECS
  `ListServerAzInfo` and paginated `ListFlavors`

The availability columns are a point-in-time view of standard, non-spot
purchase availability. They do not claim that a flavor is available under
every billing term or to every account. The total shown on each page is the
number of unique instance type IDs returned by the specification APIs; a type
with no currently reported standard purchase availability remains in the
catalog with zero covered regions and zones.

## Updating the catalogs

The fork's `Daily GitHub Pages` workflow refreshes all four catalogs before
every scheduled Pages build. It runs daily at 02:23 Asia/Shanghai and can also
be started manually. A successful build publishes the normalized raw snapshot
at `/data/china-clouds.json`, in addition to embedding it in the four catalog
pages.

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
The keys must be allowed to call the APIs listed above. In particular, Huawei
Cloud requires `ecs:cloudServerFlavors:get` for flavors and
`ecs:cloudServers:listServersDetails` for availability zones; the update fails
instead of publishing incomplete AZ coverage when either call is denied.
If Huawei IAM lists a region that the collector account has not opened, the
exact `APIGW.0802` response is reported in `skippedRegions`; other permission
errors still fail the update.

The validation test in `next/utils/regionalClouds.test.ts` checks minimum
coverage, unique identifiers, positive CPU/memory values, and official source
hosts. Python unit tests cover pagination parsing, availability merging, and
normalization. If a provider API fails or returns an implausibly small catalog,
the Pages workflow fails and the previously deployed site remains online.
