import { describe, expect, test } from "vitest";
import {
    regionalCloudProviders,
    regionalCloudSlugs,
} from "@/data/regionalClouds";

const officialSourceHosts = new Set([
    "www.alibabacloud.com",
    "help.aliyun.com",
    "intl.cloud.tencent.com",
    "cloud.tencent.com",
    "api.volcengine.com",
    "support.huaweicloud.com",
]);

describe("regional cloud catalog data", () => {
    test("contains every supported provider", () => {
        expect(Object.keys(regionalCloudProviders).sort()).toEqual(
            [...regionalCloudSlugs].sort(),
        );
    });

    for (const slug of regionalCloudSlugs) {
        const provider = regionalCloudProviders[slug];

        test(`${slug} has a useful and internally consistent catalog`, () => {
            expect(provider.instances.length).toBeGreaterThanOrEqual(
                provider.dataSource === "api" ? 20 : 12,
            );
            expect(
                new Set(provider.instances.map((item) => item.family)).size,
            ).toBeGreaterThanOrEqual(3);

            const instanceTypes = provider.instances.map(
                (item) => item.instanceType,
            );
            expect(new Set(instanceTypes).size).toBe(instanceTypes.length);

            for (const instance of provider.instances) {
                expect(instance.vCPU).toBeGreaterThan(0);
                expect(instance.memoryGiB).toBeGreaterThan(0);
                expect(instance.memoryGiB / instance.vCPU).toBeGreaterThan(0);
                expect(officialSourceHosts).toContain(
                    new URL(instance.sourceUrl).hostname,
                );
                if (provider.dataSource === "api") {
                    expect(instance.availableRegionCount).toBe(
                        instance.regions?.length,
                    );
                    expect(instance.availableZoneCount).toBe(
                        instance.zones?.length,
                    );
                }
                for (const [region, price] of Object.entries(
                    instance.onDemandPrices ?? {},
                )) {
                    expect(instance.regions).toContain(region);
                    expect(Number(price.amount)).toBeGreaterThan(0);
                    expect(["CNY", "USD"]).toContain(price.currency);
                    expect(price.unit).toBe("hour");
                }
            }

            if (provider.dataSource === "api") {
                expect(provider.generatedAt).toMatch(
                    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/,
                );
                expect(provider.regionCount).toBeGreaterThan(0);
                expect(provider.zoneCount).toBeGreaterThan(0);
                expect(
                    provider.instances.some(
                        (instance) =>
                            (instance.availableRegionCount ?? 0) > 0 &&
                            (instance.availableZoneCount ?? 0) > 0,
                    ),
                ).toBe(true);
            }
        });
    }
});
