import { describe, expect, test } from "vitest";
import {
    regionalCloudProviders,
    regionalCloudSlugs,
} from "@/data/regionalClouds";

const officialSourceHosts = new Set([
    "www.alibabacloud.com",
    "intl.cloud.tencent.com",
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
            expect(provider.instances.length).toBeGreaterThanOrEqual(12);
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
            }
        });
    }
});
