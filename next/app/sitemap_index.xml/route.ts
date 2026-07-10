import { urlInject } from "@/utils/urlInject";

export const dynamic = "force-static";

export async function GET() {
    const instanceSitemaps = [
        "/aws/ec2/sitemap-instances.xml",
        "/aws/rds/sitemap-instances.xml",
        "/aws/elasticache/sitemap-instances.xml",
        "/aws/redshift/sitemap-instances.xml",
        "/aws/opensearch/sitemap-instances.xml",
        "/azure/vm/sitemap-instances.xml",
        "/gcp/sitemap-instances.xml",
    ];
    const locations =
        process.env.PAGES_LITE_BUILD === "1"
            ? ["/sitemap-other.xml"]
            : [...instanceSitemaps, "/sitemap-other.xml"];

    const entries = locations
        .map(
            (location) => urlInject`    <sitemap>
        <loc>${location}</loc>
    </sitemap>`,
        )
        .join("\n");
    const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries}
</sitemapindex>`;
    return new Response(sitemap, {
        headers: { "Content-Type": "application/xml" },
    });
}
