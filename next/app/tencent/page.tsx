import RegionalCloudCatalog from "@/components/RegionalCloudCatalog";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Tencent Cloud CVM Instance Comparison",
    description:
        "Compare representative Tencent Cloud CVM instance families, processors, vCPUs, memory, architecture, and network performance.",
};

export default function TencentCloudPage() {
    return <RegionalCloudCatalog provider={regionalCloudProviders.tencent} />;
}
