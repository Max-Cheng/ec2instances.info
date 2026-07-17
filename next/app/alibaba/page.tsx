import RegionalCloudCatalog from "@/components/RegionalCloudCatalog";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Alibaba Cloud ECS Instance Comparison",
    description:
        "Compare Alibaba Cloud ECS instance types, processors, vCPUs, memory, architecture, network performance, and regional availability.",
};

export default function AlibabaCloudPage() {
    return <RegionalCloudCatalog provider={regionalCloudProviders.alibaba} />;
}
