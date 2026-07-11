# Entroping Launch Site and Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan. This issue uses
> one bounded implementation worker for all tasks and parent-Codex review after
> the worker handoff. Do not spawn additional agents.

**Goal:** Replace MkDocs with a branded static launch site and a custom
Starlight documentation experience that reads canonical Markdown directly from
`docs/`.

**Architecture:** Astro 7 owns one static build. A bespoke Astro page renders
the launch surface at `/`, while Starlight renders a curated documentation
collection under `/docs/`. `site/public-docs.json` is the shared public-nav
manifest; Astro's content loader and Python tests both consume it so public
navigation never drifts from canonical source paths.

**Tech Stack:** Node 24, npm 11, Astro 7.0.7, Starlight 0.41.3,
Space Grotesk Variable 5.2.10, JetBrains Mono Variable 5.2.8, TypeScript 6.0.3,
Astro Check 0.9.9, Python/pytest repository guard tests, GitHub Pages.

## Global Constraints

- Work only in the issue #1507 worktree on `feat/launch-site-docs`.
- Implement only GitHub issue #1507.
- Read and follow `AGENTS.md`, `DESIGN.md`, and
  `docs/superpowers/specs/2026-07-11-launch-site-docs-design.md` before editing.
- Preserve the approved reference
  `docs/assets/launch/launch-site-concept-mobile.gif`.
- Keep existing `docs/` Markdown canonical. Do not add a tracked duplicate docs
  tree.
- Preserve the locked CLI, runtime, Hurl, QAnstitution, traffic, provider,
  report-schema, and security behavior.
- Use Astro components and CSS. Do not add React, Tailwind, a UI kit, or client
  hydration that is not necessary.
- Do not use runtime randomness for decorative glyphs.
- Do not commit, push, open a PR, merge, or close the issue. Parent Codex owns
  integration and final Git actions.
- Verification lane is `release-ci-architecture`.

---

### Task 1: Replace the MkDocs navigation contract with a public-docs manifest

**Files:**

- Create: `site/public-docs.json`
- Create: `tests/_public_docs.py`
- Rewrite: `tests/test_public_docs_site.py`
- Modify: `tests/test_qanstitution_first_hour_docs.py`
- Modify: `tests/test_release_docs.py`
- Modify: `tests/test_homebrew_tap_prototype.py`
- Modify: `tests/test_qanstitution_schema.py`
- Modify: `tests/test_threat_model_docs.py`
- Modify: `tests/test_open_core_boundaries.py`
- Modify: `tests/test_downstream_feedback_kit_docs.py`
- Modify: `tests/test_policy_pack_distribution_docs.py`
- Modify: `tests/test_policy_pack_layout_docs.py`
- Modify: `tests/test_ci_provider_recipes_docs.py`
- Modify: `tests/test_studio_mutation_workflow_design.py`

**Interfaces:**

- Consumes: canonical Markdown paths under `docs/`.
- Produces: `PUBLIC_DOCS_MANIFEST`, `public_doc_sources()`,
  `public_doc_slugs()`, and `public_sidebar_labels()` in `tests/_public_docs.py`.
- Produces JSON groups with `{ label, collapsed?, items[] }`, where each item is
  either `{ label, source, slug }` or `{ label, url }`.

- [ ] **Step 1: Write the new manifest tests before creating the manifest**

  Rewrite `tests/test_public_docs_site.py` to assert all of the following:

  ```python
  MANIFEST = REPO_ROOT / "site" / "public-docs.json"
  PACKAGE = REPO_ROOT / "package.json"
  ASTRO_CONFIG = REPO_ROOT / "astro.config.mjs"

  def test_public_docs_manifest_uses_canonical_markdown() -> None:
      sources = public_doc_sources()
      assert "docs/index.md" in sources
      assert "docs/user/QANSTITUTION_FIRST_HOUR.md" in sources
      assert "docs/technical/QANSTITUTION_REFERENCE.md" in sources
      assert "docs/technical/TDS.md" in sources
      assert all((REPO_ROOT / source).is_file() for source in sources)
      assert len(sources) == len(set(sources))

  def test_public_docs_manifest_keeps_internal_context_out_of_navigation() -> None:
      sources = public_doc_sources()
      assert not any("prompt-library" in source for source in sources)
      assert not any("AGENT_CONTROL_PLANE" in source for source in sources)
      assert not any("docs/evolution/" in source for source in sources)

  def test_site_scaffold_is_astro_not_mkdocs() -> None:
      assert not (REPO_ROOT / "mkdocs.yml").exists()
      package = json.loads(PACKAGE.read_text(encoding="utf-8"))
      assert package["scripts"]["build"] == "astro build"
      assert "@astrojs/starlight" in package["dependencies"]
      assert "docsSchema" in ASTRO_CONFIG.read_text(encoding="utf-8") or (
          REPO_ROOT / "src" / "content.config.ts"
      ).is_file()
  ```

  Preserve the existing least-privilege Pages assertions, but update expected
  commands to `npm ci`, `npm run check`, `npm run build`, and artifact `dist`.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

  Run:

  ```bash
  uv run pytest tests/test_public_docs_site.py -q
  ```

  Expected: fail because `site/public-docs.json`, `package.json`, and Astro
  configuration do not exist and `mkdocs.yml` still exists.

- [ ] **Step 3: Add the curated manifest and shared test helper**

  Use the current MkDocs navigation as the minimum content set. Routes must be
  prefixed with `docs/` and use lower-case URL-safe slugs. Include these groups:

  ```json
  {
    "groups": [
      {"label": "Introduction", "items": [
        {"label": "Overview", "source": "docs/index.md", "slug": "docs"}
      ]},
      {"label": "Getting started", "items": [
        {"label": "QAnstitution First Hour", "source": "docs/user/QANSTITUTION_FIRST_HOUR.md", "slug": "docs/user/qanstitution-first-hour"},
        {"label": "Two-Minute Demo Assets", "source": "docs/assets/launch/README.md", "slug": "docs/assets/launch"}
      ]},
      {"label": "User guide", "items": [
        {"label": "User Guide", "source": "docs/user/USER_GUIDE.md", "slug": "docs/user/user-guide"},
        {"label": "Use Cases", "source": "docs/user/USE_CASES.md", "slug": "docs/user/use-cases"},
        {"label": "AI Provider Setup", "source": "docs/user/AI_PROVIDER_SETUP.md", "slug": "docs/user/ai-provider-setup"},
        {"label": "Drift Baseline Workflow", "source": "docs/user/DRIFT_BASELINE_WORKFLOW.md", "slug": "docs/user/drift-baseline-workflow"}
      ]}
    ],
    "external": [
      {"label": "Roadmap", "url": "https://github.com/sakibshuvo/Entroping/blob/main/ROADMAP.md"}
    ]
  }
  ```

  Add the Policy, CI/Reports, Technical Reference, and collapsed Maintainer
  Reference items from `mkdocs.yml` without omitting an existing public entry.

- [ ] **Step 4: Migrate all tests that read `mkdocs.yml`**

  Replace direct YAML reads with `public_doc_sources()` or manifest label/slug
  assertions. Preserve the original intent of every test: a required public
  doc remains public, maintainer docs remain after first-hour content, and the
  roadmap remains an external link.

- [ ] **Step 5: Run the documentation-manifest test slice**

  Run:

  ```bash
  uv run pytest \
    tests/test_public_docs_site.py \
    tests/test_qanstitution_first_hour_docs.py \
    tests/test_release_docs.py \
    tests/test_homebrew_tap_prototype.py \
    tests/test_qanstitution_schema.py \
    tests/test_threat_model_docs.py \
    tests/test_open_core_boundaries.py \
    tests/test_downstream_feedback_kit_docs.py \
    tests/test_policy_pack_distribution_docs.py \
    tests/test_policy_pack_layout_docs.py \
    tests/test_ci_provider_recipes_docs.py \
    tests/test_studio_mutation_workflow_design.py -q
  ```

  Expected: manifest-content assertions pass; Astro/workflow assertions may
  remain red until Tasks 2 and 6.

---

### Task 2: Add the Astro and Starlight static-site foundation

**Files:**

- Create: `package.json`
- Create: `package-lock.json`
- Create: `astro.config.mjs`
- Create: `tsconfig.json`
- Create: `src/content.config.ts`
- Create: `src/config/public-docs.ts`
- Create: `src/components/docs/Empty.astro`
- Create: `src/components/docs/SiteTitle.astro`
- Create: `src/styles/tokens.css`
- Create: `src/styles/docs.css`
- Create: `public/favicon.svg`
- Create: `public/robots.txt`
- Modify: `.gitignore`
- Delete: `mkdocs.yml`

**Interfaces:**

- Consumes: `site/public-docs.json`.
- Produces: `publicDocSources`, `starlightSidebar`, and `docIdForSource()` from
  `src/config/public-docs.ts`.
- Produces: Starlight `docs` collection IDs matching manifest slugs.

- [ ] **Step 1: Add exact dependency and script contracts**

  `package.json` must include:

  ```json
  {
    "private": true,
    "type": "module",
    "engines": {"node": ">=22.12.0"},
    "scripts": {
      "dev": "astro dev",
      "build": "astro build",
      "check": "astro check",
      "preview": "astro preview",
      "format": "prettier --write .",
      "format:check": "prettier --check .",
      "test:site": "node scripts/check-site-build.mjs"
    },
    "dependencies": {
      "@astrojs/starlight": "0.41.3",
      "@fontsource-variable/jetbrains-mono": "5.2.8",
      "@fontsource-variable/space-grotesk": "5.2.10",
      "astro": "7.0.7"
    },
    "devDependencies": {
      "@astrojs/check": "0.9.9",
      "prettier": "3.9.5",
      "prettier-plugin-astro": "0.14.1",
      "typescript": "6.0.3"
    }
  }
  ```

  Add `node_modules/`, `.astro/`, and `.pagefind/` to `.gitignore`.

- [ ] **Step 2: Implement the manifest adapter and content collection**

  `src/config/public-docs.ts` must validate duplicate sources/slugs at module
  load and expose Starlight sidebar objects. `src/content.config.ts` must use
  Astro's `glob()` loader with the exact manifest source paths, `base: './docs'`,
  `docsSchema()`, and a deterministic `generateId()` that returns each item's
  manifest slug.

  Extend `docsSchema()` to accept existing optional frontmatter fields:
  `type`, `status`, and `tags`.

- [ ] **Step 3: Configure Astro and Starlight**

  `astro.config.mjs` must set:

  ```js
  site: 'https://sakibshuvo.github.io',
  base: '/Entroping',
  output: 'static'
  ```

  Starlight must set the Entroping title/description, curated sidebar,
  `customCss`, GitHub social/edit links, last-updated metadata, Pagefind search,
  and component overrides for `SiteTitle`, `ThemeSelect`, and
  `MobileMenuFooter` so the public experience remains intentionally light.

- [ ] **Step 4: Install with the lockfile and run type checks**

  Run:

  ```bash
  npm install
  npm run check
  ```

  Expected: dependency installation succeeds and Astro reports zero errors.

- [ ] **Step 5: Run the first production build**

  Run:

  ```bash
  npm run build
  ```

  Expected: static output includes `dist/index.html`, `dist/docs/index.html`,
  and representative nested docs routes. Resolve loader/frontmatter/link errors
  before continuing.

---

### Task 3: Implement design-system primitives before page composition

**Files:**

- Create: `src/layouts/LaunchLayout.astro`
- Create: `src/components/BrandLockup.astro`
- Create: `src/components/Icon.astro`
- Create: `src/components/TiltButton.astro`
- Create: `src/components/KineticGlyphField.astro`
- Create: `src/components/PassMatrix.astro`
- Create: `src/components/ProofRail.astro`
- Create: `src/components/CodeWindow.astro`
- Create: `src/components/SectionBand.astro`
- Create: `src/styles/global.css`
- Temporarily create, visually inspect, then remove:
  `src/pages/_design-system.astro`

**Interfaces:**

- `TiltButton.astro` props: `href`, `variant: 'primary' | 'secondary'`,
  `icon: 'play' | 'book' | 'arrow'`, and default slot label.
- `KineticGlyphField.astro` props: `density: 'hero' | 'section' | 'docs'`.
- `PassMatrix.astro` props: `compact?: boolean`.
- `ProofRail.astro` consumes a readonly array of `{ title, body, accent }`.
- `CodeWindow.astro` props: `label`, `code`, and optional `result`.

- [ ] **Step 1: Implement tokens from `DESIGN.md` exactly**

  Put all color, spacing, motion, radius, border, and shadow custom properties
  in `tokens.css`. Component CSS may only reference these tokens or typed layout
  values documented in `DESIGN.md`.

- [ ] **Step 2: Implement deterministic decorative data**

  `KineticGlyphField.astro` must contain a stable typed array of code-native
  marks and CSS custom properties. Do not call `Math.random()` in build or
  client code. Mark the rendered field `aria-hidden="true"`.

- [ ] **Step 3: Implement all interaction states**

  Tilt buttons must visibly exercise default, hover, active, focus-visible, and
  disabled/busy styling. Primary and secondary buttons tilt in opposite
  directions. Copy controls in `CodeWindow` expose polite success/failure
  status without hiding the code when JavaScript fails.

- [ ] **Step 4: Build and inspect the temporary primitive showcase**

  Show every primitive and interaction state at `/_design-system/`. Run the dev
  server and inspect at `375px`, `768px`, and `1280px`. Fix token or state drift,
  then remove the temporary route before final handoff.

---

### Task 4: Compose the full launch page from approved primitives

**Files:**

- Create: `src/components/LaunchNav.astro`
- Create: `src/components/HeroSection.astro`
- Create: `src/components/ChaosProofSection.astro`
- Create: `src/components/DemoSection.astro`
- Create: `src/components/PhilosophySection.astro`
- Create: `src/components/ScopeSection.astro`
- Create: `src/components/LaunchFooter.astro`
- Create: `src/pages/index.astro`
- Create: `src/pages/404.astro`

**Interfaces:**

- The launch page composes sections only; reusable styling stays in primitives
  and tokens.
- All internal URLs are built from `import.meta.env.BASE_URL` or a small shared
  base-path helper. No hard-coded root-relative `/docs/` link may break the
  GitHub Pages project path.

- [ ] **Step 1: Implement the header and approved hero copy**

  DOM order must read:

  ```text
  Code at the speed of AI. Don't crash at the speed of AI.
  AI can suggest. Runtime truth decides.
  ```

  Match the mobile reference's relative type scale, coral/cobalt emphasis,
  glyph density, PASS payoff, and CTA hierarchy. The primary and secondary CTA
  labels and destinations are locked by the design spec.

- [ ] **Step 2: Implement proof and demo sections with evidence-backed copy**

  Use only commands and claims already present in `README.md` and
  `docs/meta/ZERO_CONFIG_DEMO_ENTRYPOINT.md`. Keep command text native and
  copyable. Do not use launch screenshots as hero assets.

- [ ] **Step 3: Implement philosophy, scope, closing CTA, and footer**

  Use open bands/rails instead of a three-card grid. Preserve alpha wording and
  link each principle to the relevant canonical docs route.

- [ ] **Step 4: Verify progressive enhancement and base-path correctness**

  With JavaScript disabled, direct navigation, CTA links, command text, and all
  launch copy remain available. Build under `/Entroping/` and verify no links
  point accidentally to the domain root.

---

### Task 5: Apply the Entroping design system to Starlight documentation

**Files:**

- Modify: `src/styles/docs.css`
- Modify: `src/components/docs/SiteTitle.astro`
- Modify: `src/components/docs/Empty.astro`
- Create: `src/components/docs/MobileMenuFooter.astro`
- Modify: `docs/index.md`

**Interfaces:**

- Preserve Starlight's default search, sidebar, table of contents, pagination,
  edit links, skip link, and code controls unless the plan explicitly names an
  override.

- [ ] **Step 1: Style the docs shell without flattening behavior**

  Use a sky-tinted header, cloud-white reading surface, ink typography, cobalt
  links, coral active navigation, lavender callouts, JetBrains Mono code, and a
  sparse low-density glyph accent. Avoid launch-level glyph density in article
  content.

- [ ] **Step 2: Remove theme selection while keeping accessible mobile nav**

  Override `ThemeSelect` with an empty component and `MobileMenuFooter` with
  useful Home/GitHub links. Do not override `Header`, `Sidebar`, `Search`, or
  `PageFrame` unless CSS cannot satisfy the approved design.

- [ ] **Step 3: Update the docs landing copy**

  Remove all MkDocs wording. Explain that the site is the curated public
  reading path built from canonical repository Markdown. Keep maintainer/history
  context below first-hour content.

- [ ] **Step 4: Build and exercise representative docs routes**

  Verify `/docs/`, QAnstitution First Hour, User Guide, QAnstitution Reference,
  Report Schemas, TDS, and one Maintainer Reference route. Exercise search,
  mobile sidebar, table of contents, pagination, and code copy.

---

### Task 6: Replace CI/Pages deployment and update durable documentation

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/pages.yml`
- Modify: `tests/test_ci_workflow.py`
- Modify: `docs/meta/PUBLIC_DOCS_SITE_DECISION.md`
- Modify: `docs/meta/DECISION_REGISTRY.yaml`
- Modify: `docs/meta/DOCS_GOVERNANCE.md`
- Modify: `docs/meta/TEST_STRATEGY.md`
- Modify: `docs/meta/PUBLIC_REPO_SURFACE.md`
- Modify: `docs/meta/PROJECT_PROGRESS.md`
- Modify: `docs/meta/VAULT_INDEX.md`
- Modify: `ROADMAP.md`
- Modify: `README.md`
- Modify: `.context/plan.md`
- Modify: `.context/changelog.md`
- Modify: `.context/lessons-learned.md`

**Interfaces:**

- CI docs job: checkout, Node 24 setup with npm cache, `npm ci`,
  `npm run format:check`, `npm run check`, `npm run build`.
- Pages build: same setup plus Pages configuration and upload of `dist`.

- [ ] **Step 1: Update workflow tests before workflow implementation**

  Change `tests/test_ci_workflow.py` and `tests/test_public_docs_site.py` to
  require pinned `actions/setup-node`, npm cache using `package-lock.json`,
  `npm ci`, checks, build, `dist` artifact, least-privilege permissions, and no
  executable MkDocs command.

- [ ] **Step 2: Run workflow tests and verify expected failure**

  Run:

  ```bash
  uv run pytest tests/test_ci_workflow.py tests/test_public_docs_site.py -q
  ```

  Expected: fail against the old MkDocs workflow.

- [ ] **Step 3: Implement CI and Pages workflows**

  Pin `actions/setup-node` by commit like existing actions. Preserve
  `persist-credentials: false`, least-privilege permissions, Pages concurrency,
  and Node 24 action runtime configuration.

- [ ] **Step 4: Preserve decision history while superseding MkDocs**

  Rewrite `PUBLIC_DOCS_SITE_DECISION.md` with an `Original decision` section and
  a dated `Superseding decision` section. Add `ENT-DEC-0021` to the decision
  registry with issue #1507 and paths to `DESIGN.md`, the spec, Astro config,
  and public-docs manifest. Do not pretend the original choice never existed.

- [ ] **Step 5: Update only now-false MkDocs references**

  Replace current-owner wording with `Astro/Starlight site` or `public web
  experience`. Preserve historical statements when explicitly labelled as
  history. Update README's public docs URL and local preview/build commands.

- [ ] **Step 6: Run workflow and docs-governance tests**

  Run:

  ```bash
  uv run pytest tests/test_ci_workflow.py tests/test_public_docs_site.py tests/test_agent_workflow_docs.py -q
  scripts/doc_governance_check.sh
  python scripts/public_claims_audit.py
  ```

  Expected: all pass.

---

### Task 7: Add deterministic production-output checks

**Files:**

- Create: `scripts/check-site-build.mjs`
- Modify: `package.json`
- Modify: `tests/test_public_docs_site.py`

**Interfaces:**

- `npm run test:site` consumes an existing `dist/` and exits non-zero on a
  missing route, broken local link, wrong base path, empty title/description,
  or generated MkDocs reference.

- [ ] **Step 1: Implement a bounded static-output validator**

  Inspect only `dist/**/*.html`. Validate required routes, parse local `href`
  and `src` attributes, ignore external/mail/hash URLs, resolve the `/Entroping/`
  base, and reject references to missing files. Do not crawl the network.

- [ ] **Step 2: Run build and static validation**

  Run:

  ```bash
  npm run build
  npm run test:site
  ```

  Expected: both exit 0 with a concise route/link count.

- [ ] **Step 3: Add repository-level contract assertions**

  Ensure Python tests require the script and `test:site` package command so the
  output validator cannot silently disappear.

---

### Task 8: Worker handoff verification

**Files:** all files changed by Tasks 1-7.

- [ ] **Step 1: Format and type-check**

  ```bash
  npm run format
  npm run format:check
  npm run check
  npm run build
  npm run test:site
  ```

- [ ] **Step 2: Run the focused Python slices**

  ```bash
  uv run pytest tests/test_public_docs_site.py tests/test_ci_workflow.py -q
  uv run pytest tests/test_agent_workflow_docs.py tests/test_doc_governance_script.py -q
  ```

- [ ] **Step 3: Run docs claims and governance gates**

  ```bash
  scripts/doc_governance_check.sh
  python scripts/public_claims_audit.py
  ```

- [ ] **Step 4: Review scope and artifacts**

  ```bash
  git status --short
  git diff --check
  git diff --stat
  git diff -- . ':!package-lock.json'
  ```

  Confirm no `node_modules`, `dist`, `.astro`, `.pagefind`, `.entroping`,
  report, provider output, secret, or unrelated runtime file is tracked.

- [ ] **Step 5: Return a worker handoff without committing**

  Report files changed, checks and exact results, known gaps, architecture and
  accessibility notes, and any part requiring parent-Codex browser repair.

---

## Parent-Codex Acceptance Work

The parent integrator, not the worker, must:

1. Read the complete diff and worker evidence.
2. Run the full `release-ci-architecture` lane:

   ```bash
   scripts/regression.sh --security
   scripts/audit_quality.sh
   ```

3. Use the in-app browser first to verify `/` and representative `/docs/`
   routes at `375px`, `768px`, and `1280px`.
4. Exercise mobile menu, docs sidebar, search, code copy, CTA links, keyboard
   focus, reduced motion, and horizontal overflow.
5. Capture the latest mobile implementation screenshot and compare it directly
   with `docs/assets/launch/launch-site-concept-mobile.gif` using `view_image`.
6. Write a fidelity ledger covering copy, hierarchy, palette, typography, glyph
   art, PASS matrix, button tilt/shadow, responsive behavior, and docs density.
7. Repair all fixable drift before final handoff.
8. Commit only after all required gates pass. Do not push or open a PR without a
   new explicit user request.
