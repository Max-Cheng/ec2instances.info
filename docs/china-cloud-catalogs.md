# China cloud instance catalogs

The Alibaba Cloud, Tencent Cloud, Volcengine, and Huawei Cloud pages are a
curated comparison of representative instance families. They use the shared
data model in `next/data/regionalClouds.ts` and the shared interactive table in
`next/components/RegionalCloudCatalog.tsx`.

These pages intentionally do not copy prices into the repository. Prices vary
by region, operating system, billing term, sales channel, and account-level
discount, so each page links to the provider's official price calculator.

## Data sources

- Alibaba Cloud ECS:
  [instance families](https://www.alibabacloud.com/help/en/ecs/user-guide/instance-families/)
- Tencent Cloud CVM:
  [instance specifications](https://intl.cloud.tencent.com/document/product/213/11518)
- Volcengine ECS:
  [DescribeInstanceTypes](https://api.volcengine.com/api-docs/view?action=DescribeInstanceTypes&serviceCode=ecs&version=2020-04-01)
- Huawei Cloud ECS:
  [ECS types](https://support.huaweicloud.com/intl/en-us/productdesc-ecs/en-us_topic_0035470096.html)

## Updating the catalogs

1. Verify each changed row against the linked official family or API
   documentation.
2. Update the provider's `lastReviewed` date.
3. Keep instance type identifiers unique within a provider.
4. Run `npm run check-types` and `npm run test` from `next/`.

The validation test in `next/data/regionalClouds.test.ts` checks minimum
coverage, unique identifiers, positive CPU/memory values, and official source
hosts. The model is deliberately provider-neutral so another catalog can be
added without cloning the page implementation.
