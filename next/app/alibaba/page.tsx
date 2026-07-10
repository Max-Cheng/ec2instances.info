import RegionalCloudCatalog from "@/components/RegionalCloudCatalog";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Alibaba Cloud ECS Instance Comparison",
    description:
        "Compare representative Alibaba Cloud ECS instance families, processors, vCPUs, memory, architecture, and network performance.",
};

export default function AlibabaCloudPage() {
    return <RegionalCloudCatalog provider={regionalCloudProviders.alibaba} />;
}
