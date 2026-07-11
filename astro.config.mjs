import starlight from "@astrojs/starlight";
import { unified } from "@astrojs/markdown-remark";
import { defineConfig } from "astro/config";

import { starlightSidebar } from "./src/config/public-docs.ts";
import { rewritePublicDocLinks } from "./src/config/rewrite-public-doc-links.ts";

const base = "/Entroping";

export default defineConfig({
  site: "https://sakibshuvo.github.io",
  base,
  output: "static",
  markdown: {
    processor: unified({
      remarkPlugins: [[rewritePublicDocLinks, { base }]],
    }),
  },
  integrations: [
    starlight({
      title: "Entroping",
      description:
        "Local-first runtime governance for AI-assisted backend development.",
      favicon: "/favicon.svg",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/sakibshuvo/Entroping",
        },
      ],
      editLink: {
        baseUrl: "https://github.com/sakibshuvo/Entroping/edit/main/",
      },
      lastUpdated: true,
      pagefind: true,
      disable404Route: true,
      sidebar: starlightSidebar,
      customCss: ["./src/styles/tokens.css", "./src/styles/docs.css"],
      components: {
        SiteTitle: "./src/components/docs/SiteTitle.astro",
        PageTitle: "./src/components/docs/Empty.astro",
        ThemeSelect: "./src/components/docs/Empty.astro",
        MobileMenuToggle: "./src/components/docs/MobileMenuToggle.astro",
        MobileMenuFooter: "./src/components/docs/MobileMenuFooter.astro",
      },
      head: [
        {
          tag: "meta",
          attrs: { name: "theme-color", content: "#d8effc" },
        },
      ],
    }),
  ],
});
