import manifest from "../../site/public-docs.json";

type PublicDocGroup = {
  readonly label: string;
  readonly collapsed?: boolean;
  readonly items: readonly PublicDocRoute[];
};

type PublicDocsManifest = {
  readonly groups: readonly PublicDocGroup[];
  readonly external: readonly PublicExternalItem[];
};

type PublicDocRoute = {
  readonly label: string;
  readonly source: string;
  readonly slug: string;
};

type PublicExternalItem = {
  readonly label: string;
  readonly url: string;
};

class PublicDocsManifestError extends Error {
  readonly field: "source" | "slug";
  readonly value: string;

  constructor(field: "source" | "slug", value: string) {
    super(`Duplicate public docs ${field}: ${value}`);
    this.name = "PublicDocsManifestError";
    this.field = field;
    this.value = value;
  }
}

class PublicDocSourceError extends Error {
  readonly source: string;

  constructor(source: string) {
    super(`Public docs source is not in the manifest: ${source}`);
    this.name = "PublicDocSourceError";
    this.source = source;
  }
}

class PublicDocsItemError extends Error {
  readonly label: string;

  constructor(label: string, reason: string) {
    super(`Invalid public docs item "${label}": ${reason}`);
    this.name = "PublicDocsItemError";
    this.label = label;
  }
}

const publicDocsManifest: PublicDocsManifest = manifest;

const publicDocRoutes = publicDocsManifest.groups.flatMap(
  (group) => group.items,
);

for (const route of publicDocRoutes) {
  if (
    route.label.length === 0 ||
    route.source.length === 0 ||
    route.slug.length === 0 ||
    "url" in route
  ) {
    throw new PublicDocsItemError(
      route.label,
      "routes require label, source, and slug only",
    );
  }
}

for (const item of publicDocsManifest.external) {
  if (item.label.length === 0 || item.url.length === 0 || "source" in item) {
    throw new PublicDocsItemError(
      item.label,
      "external items require label and url only",
    );
  }
}

function assertUnique(
  values: readonly string[],
  field: "source" | "slug",
): void {
  const seen = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) {
      throw new PublicDocsManifestError(field, value);
    }
    seen.add(value);
  }
}

assertUnique(
  publicDocRoutes.map((item) => item.source),
  "source",
);
assertUnique(
  publicDocRoutes.map((item) => item.slug),
  "slug",
);

const slugBySource = new Map(
  publicDocRoutes.map((item) => [item.source, item.slug]),
);

export const publicDocSources: readonly string[] = publicDocRoutes.map(
  (item) => item.source,
);

export const starlightSidebar = [
  ...publicDocsManifest.groups.map((group) => ({
    label: group.label,
    collapsed: group.collapsed ?? false,
    items: group.items.map((item) => ({
      label: item.label,
      link: `/${item.slug}/`,
    })),
  })),
  ...publicDocsManifest.external.map((item) => ({
    label: item.label,
    link: item.url,
  })),
];

export function docIdForSource(source: string): string {
  const slug = slugBySource.get(source);
  if (slug === undefined) {
    throw new PublicDocSourceError(source);
  }
  return slug;
}

export function publicDocSlugForSource(source: string): string | undefined {
  return slugBySource.get(source);
}
