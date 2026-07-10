"use client";

import { translationToolDetected } from "@/state";
import Link from "next/link";
import { forwardRef } from "react";
import { rawAnchorHref } from "@/utils/deploymentPaths";

export default forwardRef(function TranslationFriendlyLink(
    props: Omit<React.ComponentProps<typeof Link>, "ref" | "href"> & {
        href: string;
    },
    ref: React.Ref<HTMLAnchorElement>,
) {
    const usesTranslationTool = translationToolDetected.use();
    if (usesTranslationTool) {
        return <a ref={ref} {...props} href={rawAnchorHref(props.href)} />;
    }
    return <Link ref={ref} {...props} />;
});
