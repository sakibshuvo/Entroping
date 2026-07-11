import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";
import { docsSchema } from "@astrojs/starlight/schema";

import { docIdForSource, publicDocSources } from "./config/public-docs";

const docsBase = "./docs";
const docsPrefix = "docs/";

const docs = defineCollection({
  loader: glob({
    base: docsBase,
    pattern: publicDocSources.map((source) => source.slice(docsPrefix.length)),
    generateId: ({ entry }) => docIdForSource(`${docsPrefix}${entry}`),
  }),
  schema: docsSchema({
    extend: z.object({
      type: z.string().optional(),
      status: z.string().optional(),
      tags: z.array(z.string()).optional(),
    }),
  }),
});

export const collections = { docs };
