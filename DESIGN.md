# Entroping Web Design System

This file is the visual implementation contract for GitHub issue #1507. The
approved mobile reference is
[`docs/assets/launch/launch-site-concept-mobile.gif`](docs/assets/launch/launch-site-concept-mobile.gif).
The reference controls hierarchy, color, typography, kinetic glyph density,
the `PASS` payoff, and tactile CTA treatment. Implementation may adapt layout
for larger viewports, but it must not reinterpret the art direction.

## 1. Atmosphere & Identity

Entroping feels like optimistic technical proof: fast, colorful creative energy
is welcome, then deterministic runtime evidence brings it into order. The
signature is a kinetic field of code-native glyphs that begins scattered and
resolves into a measured pixel grid and green `PASS`. The surface is playful
without becoming childish, calm without becoming sterile, and technical
without defaulting to a dark terminal aesthetic.

The launch page is the expressive surface. Documentation uses the same tokens,
typography, glyph language, hard shadows, and verification motif at a lower
density so long-form reading remains comfortable.

## 2. Color

### Palette

The website is light-first. No dark theme is included in this issue.

| Role | Token | Value | Usage |
| --- | --- | --- | --- |
| Sky canvas | `--color-sky` | `#d8effc` | Launch hero and branded docs header |
| Sky strong | `--color-sky-strong` | `#b9def5` | Decorative bands and hover surfaces |
| Cloud surface | `--color-cloud` | `#fffaf3` | Reading surfaces and section contrast |
| Paper surface | `--color-paper` | `#ffffff` | Docs content, search, code-copy controls |
| Ink | `--color-ink` | `#0a1b47` | Primary text, outlines, hard shadows |
| Ink muted | `--color-ink-muted` | `#4a587a` | Supporting copy and metadata |
| Cobalt | `--color-cobalt` | `#2850d8` | Primary action, links, headline emphasis |
| Cobalt hover | `--color-cobalt-hover` | `#173bb7` | Primary action hover/active |
| Coral | `--color-coral` | `#ff654a` | `Don't crash` emphasis and active accents |
| Lavender | `--color-lavender` | `#8c78d8` | Secondary emphasis and code glyphs |
| Lavender soft | `--color-lavender-soft` | `#e9e2fb` | Secondary action and docs callouts |
| Sage | `--color-sage` | `#719b5d` | Supporting glyphs and resolved states |
| Pass green | `--color-pass` | `#4f873f` | Verified status and `PASS` matrix only |
| Butter | `--color-butter` | `#f4b934` | Underlines and sparse energetic accents |
| Coral soft | `--color-coral-soft` | `#ffe2d9` | Low-intensity highlighted surfaces |
| Border soft | `--color-border-soft` | `#b5c8db` | Reading-surface separators |
| Focus | `--color-focus` | `#173bb7` | Keyboard focus ring |

### Rules

- `--color-sky` must remain the dominant launch color.
- `--color-ink` owns all outlines and hard shadows; do not introduce neutral
  black shadows.
- Coral, lavender, sage, and butter form a controlled rhythm. A single region
  should use at most three accents plus ink and its surface.
- `--color-pass` is semantic. Reserve it for verified outcomes, checkmarks, and
  the resolved end of the entropy field.
- Gradients are not part of the approved reference. Use flat matte fields.
- Raw hex values are forbidden in component styles. Add a token here first.

## 3. Typography

### Font Stack

- Display and body: `"Space Grotesk Variable", "Space Grotesk", system-ui, sans-serif`
- Technical labels and code: `"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, monospace`
- No serif font is used.

### Scale

| Level | Size | Weight | Line height | Tracking | Usage |
| --- | --- | --- | --- | --- | --- |
| Hero/display | `clamp(3rem, 14.5vw, 9.5rem)` | 700 | `0.84` | `-0.065em` | Full launch statement |
| Section/display | `clamp(3rem, 9vw, 7rem)` | 700 | `0.9` | `-0.055em` | `Chaos in. Proof out.` and closing CTA |
| H1/docs | `clamp(2.5rem, 5vw, 4.5rem)` | 700 | `0.98` | `-0.04em` | Documentation page title |
| H2 | `clamp(2rem, 4vw, 3.5rem)` | 650 | `1.02` | `-0.035em` | Major section heading |
| H3 | `clamp(1.4rem, 2vw, 2rem)` | 650 | `1.12` | `-0.02em` | Subsection heading |
| Lead | `clamp(1.2rem, 2vw, 1.6rem)` | 500 | `1.35` | `-0.015em` | Product philosophy and section lead |
| Body large | `1.125rem` | 450 | `1.65` | `-0.01em` | Launch supporting copy |
| Body | `1rem` | 425 | `1.7` | `0` | Documentation prose |
| Body small | `0.875rem` | 500 | `1.5` | `0` | Metadata and secondary labels |
| Mono label | `0.8rem` | 600 | `1.35` | `0.025em` | API methods and glyph annotations |

### Rules

- The hero statement intentionally wraps across multiple lines on mobile; that
  is part of the approved composition, not a defect.
- `Code at the speed of AI.` and `Don't crash at the speed of AI.` must both
  carry display weight. `Don't crash` is the strongest beat, but the first
  clause may not collapse into eyebrow copy.
- `AI` is cobalt. `Don't crash` is coral with an ink hard-shadow offset.
- Documentation body text never falls below `1rem`.
- Use a maximum prose measure of `72ch` and a default docs measure near `66ch`.

## 4. Spacing & Layout

### Base Unit

All spacing is based on `4px`.

| Token | Value | Usage |
| --- | --- | --- |
| `--space-1` | `0.25rem` | Glyph micro-gap |
| `--space-2` | `0.5rem` | Inline icon gap |
| `--space-3` | `0.75rem` | Compact control padding |
| `--space-4` | `1rem` | Mobile gutter minimum |
| `--space-5` | `1.25rem` | Button internal gap |
| `--space-6` | `1.5rem` | Component padding |
| `--space-8` | `2rem` | Content group separation |
| `--space-10` | `2.5rem` | Hero rhythm step |
| `--space-12` | `3rem` | Section inner spacing |
| `--space-16` | `4rem` | Mobile section boundary |
| `--space-20` | `5rem` | Desktop section boundary |
| `--space-24` | `6rem` | Major desktop whitespace |
| `--space-32` | `8rem` | Large editorial transition |

### Grid

- Maximum launch width: `90rem`.
- Maximum documentation shell width: `96rem`.
- Mobile gutter: `clamp(1rem, 5vw, 2rem)`.
- Desktop gutter: `clamp(2rem, 5vw, 5rem)`.
- Breakpoints: `30rem`, `48rem`, `64rem`, and `80rem`.
- Mobile launches as one editorial column. At `48rem`, proof sections can use
  two columns. At `64rem`, the hero uses a twelve-column field while preserving
  the same type-first scan order.
- The bottom of each major section reveals enough of the next section to make
  scrolling feel continuous.

### Rules

- Open layout is preferred to cards. A border or panel must communicate real
  grouping.
- Asymmetry is deliberate: glyph crops, headline indentation, and button tilt
  provide rhythm while content alignment remains stable.
- No horizontal page overflow at `320px` or wider.

### Shape

| Token | Value | Usage |
| --- | --- | --- |
| `--radius-sm` | `0.375rem` | Focusable text links and compact controls |
| `--radius-md` | `0.75rem` | Code windows, docs surfaces, and status panels |
| `--radius-lg` | `1rem` | Expressive launch CTAs |

### Radius

| Token | Value | Usage |
| --- | --- | --- |
| `--radius-sm` | `0.375rem` | Focus outlines and compact controls |
| `--radius-md` | `0.75rem` | Code windows and documentation controls |
| `--radius-lg` | `1rem` | Launch CTAs and expressive proof objects |

## 5. Components

### Brand Lockup

- **Structure:** text-based `Entroping` wordmark plus optional compact three-bar
  mark. The first release may use the wordmark alone.
- **Variants:** launch, docs, footer.
- **Spacing:** `--space-2` to `--space-4`.
- **States:** link default, hover, active, focus-visible.
- **Accessibility:** accessible name is always `Entroping home`.
- **Motion:** none.

### Launch Navigation

- **Structure:** brand link, `Docs`, `GitHub`, and one menu button on compact
  viewports.
- **Variants:** expanded desktop and disclosure-based mobile.
- **States:** default, hover, active, focus-visible, menu open, menu closed.
- **Accessibility:** semantic `nav`; menu state uses `aria-expanded` and a
  labelled target.
- **Motion:** opacity and transform only, `--motion-standard`.

### Kinetic Glyph Field

- **Structure:** deterministic array of decorative code glyphs positioned by
  CSS custom properties; no runtime randomness.
- **Variants:** hero high-density, section medium-density, docs low-density.
- **States:** decorative only.
- **Accessibility:** entire field is `aria-hidden="true"` and cannot receive
  focus.
- **Motion:** glyphs enter scattered and settle by transform/opacity. Reduced
  motion renders the final state immediately.

### Hero Statement

- **Structure:** semantic `h1` containing two sentence spans and emphasis spans
  for `AI` and `Don't crash`, followed by the visible two-line mono annotation
  `// write fast` / `verify faster` from the approved reference.
- **Variants:** mobile stacked and desktop editorial grid.
- **Accessibility:** DOM order remains the spoken sentence order even when CSS
  offsets the visual rhythm; the annotation remains a separate paragraph so it
  does not alter the heading's accessible name.
- **Motion:** one transform/opacity entrance sequence; no character-by-character
  animation.

### Pass Matrix

- **Structure:** code-native grid with a pixel checkmark and a text `PASS`
  label. The visual cells are decorative; screen readers receive a concise
  `Verified: PASS` status string.
- **Variants:** full launch payoff and compact docs status motif.
- **States:** neutral before reveal, pass after reveal.
- **Motion:** rows settle into alignment; never flashes or pulses.

### Tilt Button

- **Structure:** semantic anchor with SVG icon, label, border, and hard shadow.
- **Variants:** primary cobalt and secondary lavender.
- **Primary default:** `rotate(-1.25deg)`; hover `rotate(-2deg) translateY(-2px)`;
  active `rotate(-0.5deg) translate(3px, 3px)` with reduced shadow.
- **Secondary default:** `rotate(0.75deg)`; hover
  `rotate(1.4deg) translateY(-2px)`; active
  `rotate(0.35deg) translate(3px, 3px)`.
- **States:** default, hover, active, focus-visible, disabled/busy.
- **Accessibility:** minimum `48px` height, visible focus ring, descriptive link
  text, decorative icons hidden.
- **Motion:** transform and shadow-color only. Reduced motion keeps static tilt
  but removes transitions.

### Proof Rail

- **Structure:** three semantic steps: QAnstitution governs, Hurl executes, CI
  keeps the receipt.
- **Variants:** vertical mobile and horizontal tablet/desktop.
- **States:** default and current proof step where interactive demonstration is
  used.
- **Accessibility:** ordered list with visible titles and complete descriptions.
- **Motion:** optional IntersectionObserver reveal using opacity/transform.

### Code Window

- **Structure:** labelled code block with native text, copy button, and expected
  proof output.
- **Variants:** demo command and result.
- **States:** default, copy hover/focus, copied confirmation, copy error.
- **Accessibility:** copy feedback uses an `aria-live="polite"` region.
- **Motion:** no content animation.

### Documentation Shell

- **Structure:** Starlight header, search, curated sidebar, article, table of
  contents, pagination, and edit link.
- **Variants:** wide three-column, tablet two-column, mobile disclosure.
- **States:** current navigation item, search open, search result focus, sidebar
  open/closed, code copied.
- **Accessibility:** preserve Starlight semantics and keyboard behavior; visual
  overrides may not remove labels, focus rings, or skip links.
- **Motion:** disclosure transitions use transform/opacity only.

### Section Band

- **Structure:** full-width semantic section with one background token and an
  inner content grid.
- **Variants:** sky, cloud, coral-soft, lavender-soft.
- **States:** static.
- **Accessibility:** heading order remains sequential.
- **Motion:** none unless a child component owns a meaningful reveal.

## 6. Motion & Interaction

### Timing

| Token | Duration | Easing | Usage |
| --- | --- | --- | --- |
| `--motion-micro` | `120ms` | `ease-out` | Button press and focus response |
| `--motion-standard` | `220ms` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | Menu and hover transitions |
| `--motion-emphasis` | `520ms` | `cubic-bezier(0.16, 1, 0.3, 1)` | Hero and proof settling |

### Rules

- Animate only `transform`, `opacity`, and a static shadow color change.
- Motion must describe entropy becoming order or communicate an interaction.
- No continuous decorative loops.
- No scroll listeners. Use CSS or `IntersectionObserver` for one-time reveals.
- `prefers-reduced-motion: reduce` disables entrances and transitions while
  keeping the final composition intact.

## 7. Depth & Surface

The depth strategy is **mixed borders and hard offset shadows**.

| Token | Value | Usage |
| --- | --- | --- |
| `--border-strong` | `2px solid var(--color-ink)` | CTA and expressive controls |
| `--border-soft` | `1px solid var(--color-border-soft)` | Docs separators and search |
| `--shadow-hard-sm` | `3px 3px 0 var(--color-ink)` | Compact controls |
| `--shadow-hard-md` | `6px 6px 0 var(--color-ink)` | Launch CTAs and proof objects |
| `--shadow-focus` | `0 0 0 4px var(--color-focus)` | Keyboard focus |
| `--shadow-focus-inverse` | `0 0 0 4px var(--color-sky-strong)` | Keyboard focus on ink surfaces |
| `--shadow-mask-sky` | `0 0 0 var(--space-2) var(--color-sky)` | Clear protected copy inside the sky glyph field |
| `--shadow-mask-cloud` | `0 0 0 var(--space-2) var(--color-cloud)` | Clear protected copy inside the cloud glyph field |

Soft blurred card shadows, glass, glow, and translucent surface stacks are not
part of the system. Documentation can use flat white surfaces separated by
tonal shifts and soft borders.
