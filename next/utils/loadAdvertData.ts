import { type MarketingSchema, validateMarketing } from "@/schemas/marketing";
import { MARKETING_JSON_URL } from "@/components/advertUrl";

async function loadAdvertData(): Promise<MarketingSchema> {
    if (process.env.NEXT_PUBLIC_REMOVE_ADVERTS === "1") {
        return { ctas: {}, promotions: {} };
    }
    const res = await fetch(MARKETING_JSON_URL);
    if (!res.ok) {
        throw new Error("Failed to fetch marketing data");
    }
    const newData = await res.json();
    return validateMarketing(newData);
}

export default loadAdvertData();
