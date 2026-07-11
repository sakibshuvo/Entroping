# Entroping Launch Site and Documentation Design

**Issue:** [#1507](https://github.com/sakibshuvo/Entroping/issues/1507)

**Status:** Approved for implementation

**Approved visual reference:**
[`docs/assets/launch/launch-site-concept-mobile.gif`](../../assets/launch/launch-site-concept-mobile.gif)

## Objective

Replace MkDocs Material with one branded static website that makes Entroping
launch-ready without forking the canonical Markdown knowledge base. The root
route sells and proves the product. `/docs/` provides a fast, searchable,
reading-first documentation experience using the same visual identity at a
lower density.

## Product Contract

The public story stays inside the current core boundary:

```text
REST/OpenAPI + QAnstitution + Hurl + CI reports
```

The launch page may explain traffic-backed regression capture as part of the
documented product, but Studio, WireMock, dependency mapping, GraphQL, SOAP,
hosted services, and speculative report surfaces may not displace the first
hour story. Public maturity remains alpha. No claim may imply autonomous merge
authority, production guarantees, or hosted availability.

## Architecture

Use Astro 7 and Starlight in a single root-level Node project.

- `src/pages/index.astro` is the bespoke launch page.
- Starlight renders documentation under `/docs/`.
- Astro's content layer reads a curated set of existing Markdown files directly
  from `docs/`; no tracked duplicate docs tree is introduced.
- A declarative `site/public-docs.json` owns the public sidebar labels, source
  paths, and route slugs. The content loader and tests consume the same file.
- Starlight supplies accessible navigation, Pagefind search, code highlighting,
  copy controls, table of contents, and pagination. Custom CSS and small
  component overrides remove the stock-theme appearance.
- Astro produces static output in `dist/` for GitHub Pages.
- `site` and `base` are set for
  `https://sakibshuvo.github.io/Entroping/`; internal links use the configured
  base path instead of root-relative assumptions.

This follows Astro's documented support for custom pages alongside Starlight
content pages, Starlight component/CSS overrides, and Astro content loaders
that read Markdown from arbitrary filesystem locations.

## Launch Information Architecture

### 1. Header

- Text wordmark `Entroping`.
- Links: `Docs`, `GitHub`.
- Mobile disclosure uses a labelled menu button.

### 2. Hero

Exact copy:

```text
Code at the speed of AI.
Don't crash at the speed of AI.

AI can suggest. Runtime truth decides.
```

- The full statement is the visual focus.
- `AI` is cobalt and `Don't crash` is coral with an ink hard shadow.
- Code glyphs begin scattered and resolve toward the `PASS` matrix.
- Primary CTA: `Run the 2-minute demo` links to `#demo`.
- Secondary CTA: `Read the docs` links to the `/docs/` entry route.
- Both buttons have opposing static tilts and meaningful hover/active movement.

### 3. Chaos In. Proof Out.

Three ordered statements:

1. `QAnstitution governs.` Policies define allowed runtime behavior.
2. `Hurl executes.` Real HTTP requests produce deterministic results.
3. `CI keeps the receipt.` JSON, JUnit, and HTML evidence survive the run.

The section starts with scattered glyphs and ends in an aligned check matrix.

### 4. Two-Minute Proof

Use the current evidence-backed commands:

```bash
git clone https://github.com/sakibshuvo/Entroping.git
cd Entroping
brew install uv hurl
scripts/demo.sh
```

Also show the installed-package path:

```bash
entroping demo --project ./entroping-checkout-demo
```

Expected proof is stated without invented metrics: Hurl passes and writes JSON,
JUnit, and HTML reports without provider or external API calls.

### 5. Philosophy Bands

Use three full-width or rail-based color moments instead of a card grid:

- `QAnstitution is Law.`
- `Traffic is Truth.`
- `Hurl is the Enforcer.`

Each band contains one concise evidence-backed explanation and a relevant docs
link. CI remaining LLM-free is stated as the closing principle.

### 6. Scope and Closing CTA

State the focused launch scope and alpha boundary. End with:

- `Run the 2-minute demo`
- `Start with the docs`
- GitHub repository link

Do not add pricing, testimonials, fake adoption metrics, integration marquees,
or email capture.

## Documentation Information Architecture

The public sidebar is curated in this order:

1. Introduction
2. Getting started
3. User guide
4. Policy and QAnstitution
5. CI and reports
6. Technical reference
7. Maintainer reference, collapsed by default
8. External roadmap link

The current MkDocs navigation is the minimum content set. The migration may
improve labels and grouping but may not expose Obsidian context, prompt-library,
agent-control, evolution, or raw source-history docs as first-level public
navigation.

## Documentation Visual Treatment

- Sky-tinted sticky header with the Entroping wordmark and sparse glyph accent.
- Cloud-white article surface with deep-ink type.
- Cobalt links, coral active markers, lavender secondary surfaces, and green
  verified callouts.
- JetBrains Mono for code and technical labels.
- Hard shadows only on primary interactive moments; ordinary reading surfaces
  use soft borders and tonal shifts.
- Search, sidebars, pagination, tables, callouts, and code blocks retain their
  accessible Starlight behavior.
- No dark-mode toggle in this issue; the public identity is intentionally light.

## Responsive Behavior

- `320-479px`: single-column hero, full-width CTAs, bottom-next-section reveal,
  mobile docs disclosure, no horizontal overflow.
- `480-767px`: larger editorial type, proof matrix gains width, CTAs remain
  stacked or fit side by side only when both retain `48px` targets.
- `768-1023px`: two-column proof/demo sections; docs sidebar becomes persistent
  when space permits.
- `1024px+`: twelve-column launch composition; hero text and glyph field share
  the viewport without changing DOM reading order.
- `1280px+`: content stops growing at the design-system maximum widths.

## Accessibility

- Semantic heading order and landmark structure.
- Decorative glyph fields are hidden from assistive technology.
- Minimum `48px` CTA targets.
- Visible `:focus-visible` treatment on every control.
- Menu and copy controls expose state and status to assistive technology.
- Color contrast meets WCAG AA for normal text and controls.
- Reduced-motion users receive the final composition with no entrance motion.
- The layout works at 200% zoom without clipping or lost functionality.

## SEO and Metadata

- Canonical site URL and GitHub Pages base path are configured once.
- Root title and description reflect local-first runtime governance.
- Documentation pages derive titles/descriptions from existing frontmatter.
- Add favicon, theme color, Open Graph metadata, and a concise 404 page.
- Sitemap or RSS is not required for this issue.

## Repository and Decision Updates

- Remove `mkdocs.yml` and all executable MkDocs build references.
- Update `.github/workflows/ci.yml` and `.github/workflows/pages.yml` to use
  Node 24, `npm ci`, checks, and the static `dist/` artifact.
- Amend `docs/meta/PUBLIC_DOCS_SITE_DECISION.md` as a superseded decision record;
  do not erase why MkDocs was originally selected.
- Add a new accepted decision to `docs/meta/DECISION_REGISTRY.yaml`.
- Update `DOCS_GOVERNANCE.md`, `TEST_STRATEGY.md`, `PUBLIC_REPO_SURFACE.md`,
  `PROJECT_PROGRESS.md`, `VAULT_INDEX.md`, `ROADMAP.md`, `README.md`, and
  `.context/` only where their current MkDocs wording would otherwise become
  false.
- Update tests that treated `mkdocs.yml` as the public-navigation API to assert
  the new declarative site manifest and Astro workflows instead.

## Error Handling and Failure Modes

- Missing canonical public docs referenced by `site/public-docs.json` fail the
  Python documentation tests before build.
- Invalid frontmatter or Markdown fails Astro/Starlight build.
- Broken internal links fail the production site check.
- The Pages job does not deploy when checks or the build fail.
- Copy-button failure leaves the code readable and reports a polite failure
  state.
- JavaScript-disabled navigation retains direct links and readable content;
  the mobile disclosure is the only progressively enhanced navigation detail.

## Verification

Verification lane: `release-ci-architecture`.

Required local evidence:

```text
npm run format:check
npm run check
npm run build
focused pytest documentation/workflow tests
scripts/doc_governance_check.sh
python scripts/public_claims_audit.py
scripts/regression.sh --security
scripts/audit_quality.sh
```

Browser QA must cover `375px`, `768px`, and `1280px`, both `/` and representative
`/docs/` routes, navigation, focus states, CTA links, search, code copy, mobile
menu, reduced motion, and horizontal overflow. Final fidelity review compares
the accepted concept and the latest mobile browser screenshot directly.

## Non-Goals

- Runtime, CLI, Hurl, QAnstitution, traffic, report-schema, provider, redaction,
  or security behavior changes.
- Redesigning generated HTML reports.
- Hosted application features, auth, analytics, billing, email capture, or a
  custom domain.
- Publishing, merging, or closing #1507 in this implementation session.
