import { describe, expect, test } from "vitest";
import type { RegionalCloudInstance } from "@/data/regionalClouds";
import {
    adaptRegionalCloudInstance,
    regionalCloudRegionIds,
} from "./regionalCloudTableAdapter";

function instance(
    instanceType: string,
    regions?: string[],
    zones?: string[],
): RegionalCloudInstance {
    return {
        instanceType,
        family: "g8i",
        familyName: "General-purpose g8i",
        category: "General purpose",
        vCPU: 3,
        memoryGiB: 10,
        architecture: "x86_64",
        processor: "Intel Xeon",
        networkPerformance: "Up to 15 Gbps",
        localStorage: "Cloud disks",
        sourceUrl:
            "https://www.alibabacloud.com/help/en/ecs/user-guide/instance-families",
        regions,
        zones,
    };
}

describe("regional cloud table adapter", () => {
    test("maps catalog fields into the shared instance table shape", () => {
        const source = {
            ...instance(
                "ecs.g8i.large",
                ["cn-beijing", "cn-shanghai"],
                ["cn-beijing-a", "cn-shanghai-b"],
            ),
            availableRegionCount: 7,
            availableZoneCount: 9,
        };

        expect(
            adaptRegionalCloudInstance(
                source,
                "https://www.alibabacloud.com/pricing/calculator",
            ),
        ).toEqual(
            expect.objectContaining({
                instanceType: "ecs.g8i.large",
                instance_type: "ecs.g8i.large",
                memoryPerVcpu: 3.33,
                pricingUrl: "https://www.alibabacloud.com/pricing/calculator",
                regions: ["cn-beijing", "cn-shanghai"],
                zones: ["cn-beijing-a", "cn-shanghai-b"],
                availableRegionCount: 7,
                availableZoneCount: 9,
            }),
        );
        expect(source).not.toHaveProperty("instance_type");
    });

    test("defaults availability arrays and counts when the API omits them", () => {
        expect(
            adaptRegionalCloudInstance(
                instance("ecs.g8i.xlarge"),
                "https://www.alibabacloud.com/pricing/calculator",
            ),
        ).toEqual(
            expect.objectContaining({
                regions: [],
                zones: [],
                availableRegionCount: 0,
                availableZoneCount: 0,
            }),
        );
    });

    test("returns unique naturally sorted region ids", () => {
        const instances = [
            adaptRegionalCloudInstance(
                instance("ecs.g8i.large", ["cn-test-10", "cn-test-2"]),
                "https://www.alibabacloud.com/pricing/calculator",
            ),
            adaptRegionalCloudInstance(
                instance("ecs.g8i.xlarge", ["cn-test-1", "cn-test-2"]),
                "https://www.alibabacloud.com/pricing/calculator",
            ),
        ];

        expect(regionalCloudRegionIds(instances)).toEqual([
            "cn-test-1",
            "cn-test-2",
            "cn-test-10",
        ]);
    });
});
