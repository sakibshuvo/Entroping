import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { publicDocSlugForSource } from "./public-docs";

type MarkdownNode = {
  type: string;
  url?: string;
  children?: MarkdownNode[];
};

type MarkdownFile = {
  readonly path?: string;
};

type RewriteOptions = {
  readonly base: string;
};

type RewriteContext = {
  readonly filePath: string;
  readonly image: boolean;
  readonly base: string;
};

class PublicDocLinkTargetError extends Error {
  readonly sourceUrl: string;
  readonly filePath: string;

  constructor(sourceUrl: string, filePath: string, reason: string) {
    super(`Invalid public docs link "${sourceUrl}" in ${filePath}: ${reason}`);
    this.name = "PublicDocLinkTargetError";
    this.sourceUrl = sourceUrl;
    this.filePath = filePath;
  }
}

const repoRoot = fileURLToPath(new URL("../../", import.meta.url));
const githubBlobBase = "https://github.com/sakibshuvo/Entroping/blob/main/";
const githubRawBase =
  "https://raw.githubusercontent.com/sakibshuvo/Entroping/main/";

function isExternalOrAnchor(url: string): boolean {
  return (
    url.startsWith("#") ||
    url.startsWith("/") ||
    /^[a-z][a-z\d+.-]*:/iu.test(url)
  );
}

function encodedRepoPath(source: string): string {
  return source.split("/").map(encodeURIComponent).join("/");
}

function rewriteUrl(url: string, context: RewriteContext): string {
  if (isExternalOrAnchor(url)) {
    return url;
  }

  const suffixIndex = url.search(/[?#]/u);
  const linkPath = suffixIndex === -1 ? url : url.slice(0, suffixIndex);
  const suffix = suffixIndex === -1 ? "" : url.slice(suffixIndex);
  if (linkPath.length === 0) {
    return url;
  }

  let decodedLinkPath: string;
  try {
    decodedLinkPath = decodeURI(linkPath);
  } catch (error) {
    if (error instanceof URIError) {
      throw new PublicDocLinkTargetError(
        url,
        context.filePath,
        "malformed URI encoding",
      );
    }
    throw error;
  }

  const absoluteTarget = path.resolve(
    path.dirname(context.filePath),
    decodedLinkPath,
  );
  if (!existsSync(absoluteTarget)) {
    throw new PublicDocLinkTargetError(
      url,
      context.filePath,
      "target does not exist",
    );
  }
  const source = path
    .relative(repoRoot, absoluteTarget)
    .split(path.sep)
    .join("/");
  if (source === ".." || source.startsWith("../")) {
    throw new PublicDocLinkTargetError(
      url,
      context.filePath,
      "target escapes the repository",
    );
  }

  const publicSlug = publicDocSlugForSource(source);
  if (publicSlug !== undefined) {
    return `${context.base}${publicSlug}/${suffix}`;
  }

  const targetBase = context.image ? githubRawBase : githubBlobBase;
  return `${targetBase}${encodedRepoPath(source)}${suffix}`;
}

function rewriteTree(node: MarkdownNode, filePath: string, base: string): void {
  if (
    (node.type === "link" || node.type === "image") &&
    node.url !== undefined
  ) {
    node.url = rewriteUrl(node.url, {
      filePath,
      image: node.type === "image",
      base,
    });
  }
  for (const child of node.children ?? []) {
    rewriteTree(child, filePath, base);
  }
}

export function rewritePublicDocLinks(options: RewriteOptions) {
  const base = options.base.endsWith("/") ? options.base : `${options.base}/`;
  return (tree: MarkdownNode, file: MarkdownFile): void => {
    if (file.path !== undefined) {
      rewriteTree(tree, file.path, base);
    }
  };
}
