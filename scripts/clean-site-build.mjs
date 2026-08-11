import { rm } from "node:fs/promises";

const repoRoot = new URL("../", import.meta.url);
const generatedPaths = [".astro", "dist", "node_modules/.astro"];

await Promise.all(
  generatedPaths.map((relativePath) =>
    rm(new URL(relativePath, repoRoot), {
      force: true,
      recursive: true,
    }),
  ),
);
