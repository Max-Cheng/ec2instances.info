function normalizedBasePath() {
    const value = process.env.NEXT_PUBLIC_BASE_PATH || "";
    if (value && (!value.startsWith("/") || value.endsWith("/"))) {
        throw new Error(
            "NEXT_PUBLIC_BASE_PATH must start with / and must not end with /",
        );
    }
    return value;
}

export function withBasePath(path: string) {
    if (!path.startsWith("/")) {
        throw new Error("A deployment path must start with /");
    }
    return `${normalizedBasePath()}${path}`;
}

export function rawAnchorHref(href: string) {
    return href.startsWith("/") ? withBasePath(href) : href;
}

export function instanceDetailHref(path: string) {
    if (!path.startsWith("/")) {
        throw new Error("An instance detail path must start with /");
    }

    const origin = process.env.NEXT_PUBLIC_INSTANCE_DETAIL_ORIGIN?.replace(
        /\/$/,
        "",
    );
    return origin ? `${origin}${path}` : path;
}
