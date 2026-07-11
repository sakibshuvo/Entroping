import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const DIST_ROOT = path.join(REPO_ROOT, "dist");
const SITE_ORIGIN = "https://sakibshuvo.github.io";
const SITE_BASE = "/Entroping/";
const REQUIRED_OUTPUTS = [
  "index.html",
  "404.html",
  "docs/index.html",
  "docs/user/qanstitution-first-hour/index.html",
  "docs/technical/tds/index.html",
];
const URL_ATTRIBUTE_PATTERN = /\b(?:href|src)=(?:"([^"]*)"|'([^']*)')/giu;
const TITLE_PATTERN = /<title(?:\s[^>]*)?>(.*?)<\/title>/isu;
const META_PATTERN = /<meta\s+[^>]*>/giu;

class SiteBuildValidationError extends Error {
  constructor(messages) {
    super(messages.join("\n"));
    this.name = "SiteBuildValidationError";
    this.messages = messages;
  }
}

async function collectHtmlFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        return collectHtmlFiles(entryPath);
      }
      return entry.isFile() && entry.name.endsWith(".html") ? [entryPath] : [];
    }),
  );
  return nested.flat().sort();
}

async function pathExists(candidate) {
  try {
    const metadata = await stat(candidate);
    return metadata.isFile();
  } catch (error) {
    if (error instanceof Error && "code" in error && error.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

function outputPageUrl(htmlPath) {
  const relativePath = path
    .relative(DIST_ROOT, htmlPath)
    .split(path.sep)
    .join("/");
  if (relativePath === "index.html") {
    return SITE_BASE;
  }
  if (relativePath.endsWith("/index.html")) {
    return `${SITE_BASE}${relativePath.slice(0, -"index.html".length)}`;
  }
  return `${SITE_BASE}${relativePath}`;
}

function localUrls(html) {
  return [...html.matchAll(URL_ATTRIBUTE_PATTERN)].map(
    (match) => match[1] ?? match[2] ?? "",
  );
}

function isIgnoredUrl(value) {
  return (
    value.length === 0 ||
    value.startsWith("#") ||
    value.startsWith("https://") ||
    value.startsWith("http://") ||
    value.startsWith("mailto:") ||
    value.startsWith("tel:") ||
    value.startsWith("data:") ||
    value.startsWith("javascript:")
  );
}

function outputCandidate(pathname) {
  const relativePath = pathname.slice(SITE_BASE.length);
  if (relativePath.length === 0) {
    return path.join(DIST_ROOT, "index.html");
  }
  if (relativePath.endsWith("/")) {
    return path.join(DIST_ROOT, relativePath, "index.html");
  }
  return path.join(DIST_ROOT, relativePath);
}

function hasDescription(html) {
  return [...html.matchAll(META_PATTERN)].some((match) => {
    const tag = match[0];
    return (
      /\bname=(?:"description"|'description')/iu.test(tag) &&
      /\bcontent=(?:"[^"]+"|'[^']+')/iu.test(tag)
    );
  });
}

async function validateHtmlFile(htmlPath) {
  const html = await readFile(htmlPath, "utf8");
  const relativePath = path.relative(REPO_ROOT, htmlPath);
  const failures = [];
  const title = TITLE_PATTERN.exec(html)?.[1]
    ?.replace(/<[^>]+>/gu, "")
    .trim();

  if (title === undefined || title.length === 0) {
    failures.push(`${relativePath}: missing or empty title`);
  }
  if (!hasDescription(html)) {
    failures.push(`${relativePath}: missing or empty description`);
  }
  if (/mkdocs/iu.test(html)) {
    failures.push(`${relativePath}: generated output still references MkDocs`);
  }

  const pageUrl = outputPageUrl(htmlPath);
  let checkedLinks = 0;
  for (const value of localUrls(html)) {
    if (isIgnoredUrl(value)) {
      continue;
    }
    checkedLinks += 1;
    const resolved = new URL(value, `${SITE_ORIGIN}${pageUrl}`);
    if (!resolved.pathname.startsWith(SITE_BASE)) {
      failures.push(`${relativePath}: URL escapes ${SITE_BASE}: ${value}`);
      continue;
    }
    const candidate = outputCandidate(decodeURIComponent(resolved.pathname));
    if (!(await pathExists(candidate))) {
      failures.push(`${relativePath}: missing local target for ${value}`);
    }
  }

  return { failures, checkedLinks };
}

async function main() {
  const missingOutputs = [];
  for (const required of REQUIRED_OUTPUTS) {
    if (!(await pathExists(path.join(DIST_ROOT, required)))) {
      missingOutputs.push(`dist/${required}: required route is missing`);
    }
  }

  const htmlFiles = await collectHtmlFiles(DIST_ROOT);
  const results = await Promise.all(htmlFiles.map(validateHtmlFile));
  const failures = [
    ...missingOutputs,
    ...results.flatMap((result) => result.failures),
  ];
  if (failures.length > 0) {
    throw new SiteBuildValidationError(failures);
  }

  const checkedLinks = results.reduce(
    (total, result) => total + result.checkedLinks,
    0,
  );
  console.log(
    `Validated ${htmlFiles.length} HTML routes and ${checkedLinks} local links under ${SITE_BASE}`,
  );
}

try {
  await main();
} catch (error) {
  if (error instanceof SiteBuildValidationError) {
    console.error(error.message);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
