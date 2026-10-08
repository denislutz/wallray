# Palette Migration Plan — "Copper Aquamarine Dream"

Goal: replace the current neutral/grayscale placeholder theme with the brand palette
(`#BFB9B5 #C35627 #4C848D #30525C #D6794D #DCAA89`), and do it in a way where **any future
palette swap is a one-block edit, never a component hunt.**

---

## 1. Current state (audit)

The design-token plumbing for this already exists and is sound — Tailwind 4 CSS-only config
in `fe/app/globals.css`, with a `@theme inline` block mapping `--color-*` Tailwind tokens to
CSS custom properties defined in `:root` / `.dark`. Every `ui/base/` primitive
(`button.tsx`, `card.tsx`, `badge.tsx`, `Text.tsx`) already consumes only semantic classes
(`bg-primary`, `text-muted-foreground`, `bg-destructive/10`, `border-border`, …) — never a raw
Tailwind palette utility or a hex value. `ui/business/LandingPage.tsx` and the new
`ui/business/landing/` copy files are equally clean.

This means the palette is **already 90% "exchangeable"** — swapping the values inside
`:root`/`.dark` reskins the entire app with zero component changes. Two leaks break that
guarantee today and must be fixed as part of this migration:

| File | Line(s) | Issue |
|---|---|---|
| `fe/ui/base/StatusDot.tsx` | 17–20, 28 | `bg-zinc-400`, `bg-emerald-500`, `bg-amber-400`, `bg-red-500`, `text-zinc-500` — raw Tailwind palette classes, invisible to a theme/palette swap |
| `fe/ui/business/ReportView.tsx` | 256, 272 | `text-amber-500`, `text-emerald-500` — same problem, inline in a business component |

Everything else in scope (`fe/ui/base/*`, `fe/ui/business/LandingPage.tsx`,
`fe/services/tech/TailwindS.ts`) needs no structural change — `TailwindS.ts` is just the
`cn()` merge helper and stays as-is.

---

## 2. Token architecture: three layers

```
Layer 1 — Palette      raw brand hues, named, hex source-of-truth        (new)
Layer 2 — Semantic     shadcn role tokens (--primary, --border, ...)      (exists)
Layer 3 — Component    ui/base/* — consumes Layer 2 classes only          (exists, 2 leaks to fix)
```

**The rule that makes a palette "always exchangeable": Layer 3 never changes.** A palette
swap only ever touches Layer 1 (and, if the new palette wants different role assignments,
the `var()` references in Layer 2 — but the *shape* of Layer 2 never changes). This is the
same pattern already used for light/dark (`.dark` overrides the same variable names) —
we're extending it to full palette swaps, not inventing a new mechanism.

### Layer 1 — palette tokens (new, added to `globals.css`)

Source hex → oklch (computed via the standard sRGB→OKLab conversion, matching the format
already used in this file):

| Swatch | Hex | oklch | Role |
|---|---|---|---|
| Stone | `#BFB9B5` | `oklch(0.790 0.009 56.3)` | neutral / border base |
| Copper | `#C35627` | `oklch(0.584 0.152 41.8)` | **primary** |
| Teal | `#4C848D` | `oklch(0.578 0.061 208.8)` | **secondary / accent** |
| Deep Teal | `#30525C` | `oklch(0.417 0.043 218.6)` | dark-mode anchor / ring |
| Terracotta | `#D6794D` | `oklch(0.670 0.130 45.2)` | primary hover / chart |
| Tan | `#DCAA89` | `oklch(0.776 0.074 54.8)` | warm tint / chart |

```css
:root {
  --palette-stone: oklch(0.790 0.009 56.3);
  --palette-copper: oklch(0.584 0.152 41.8);
  --palette-teal: oklch(0.578 0.061 208.8);
  --palette-deep-teal: oklch(0.417 0.043 218.6);
  --palette-terracotta: oklch(0.670 0.130 45.2);
  --palette-tan: oklch(0.776 0.074 54.8);
}
```

This block is **the entire surface a future palette swap touches.** Six named values,
hex noted in a comment above each for traceability back to the source swatch.

### Layer 2 — semantic tokens (existing shape, new values)

Role assignment rationale: copper (warm, high-energy) reads as "flag an issue" — right fit
for a defect-inspection product's primary action color. Teal is the trust/professional
counterpoint used for secondary surfaces and the accent role. Stone anchors neutral
surfaces/borders so the brand hues don't have to carry structural weight.

```css
:root {
  --background: oklch(0.984 0.006 60);            /* was 0.004 75 — warm-shifted, barely visible */
  --foreground: oklch(0.205 0.02 220);             /* deep-teal-tinted near-black, was pure gray */
  --card: oklch(0.995 0.004 60);
  --card-foreground: var(--foreground);
  --popover: var(--card);
  --popover-foreground: var(--foreground);

  --primary: var(--palette-copper);
  --primary-foreground: oklch(0.985 0.004 60);

  --secondary: oklch(0.93 0.02 208);               /* pale teal surface */
  --secondary-foreground: var(--palette-deep-teal);

  --muted: oklch(0.955 0.008 60);
  --muted-foreground: oklch(0.5 0.02 220);

  --accent: var(--palette-teal);
  --accent-foreground: oklch(0.985 0.004 60);

  --destructive: oklch(0.577 0.245 27.325);        /* unchanged — status color, see §3 */

  --border: oklch(0.85 0.012 56);                  /* palette-stone, lightened for hairlines */
  --input: var(--border);
  --ring: var(--palette-teal);

  --chart-1: var(--palette-copper);
  --chart-2: var(--palette-teal);
  --chart-3: var(--palette-terracotta);
  --chart-4: var(--palette-deep-teal);
  --chart-5: var(--palette-tan);
}

.dark {
  --background: oklch(0.19 0.015 220);             /* deep-teal-tinted near-black, not neutral gray */
  --foreground: oklch(0.94 0.006 60);
  --card: oklch(0.24 0.018 220);
  --card-foreground: var(--foreground);
  --popover: var(--card);
  --popover-foreground: var(--foreground);

  --primary: var(--palette-terracotta);            /* lighter copper — keeps contrast on dark bg */
  --primary-foreground: oklch(0.19 0.015 220);

  --secondary: oklch(0.3 0.02 220);
  --secondary-foreground: oklch(0.9 0.01 208);

  --muted: oklch(0.28 0.015 220);
  --muted-foreground: oklch(0.65 0.015 220);

  --accent: var(--palette-teal);
  --accent-foreground: oklch(0.97 0.004 60);

  --destructive: oklch(0.704 0.191 22.216);         /* unchanged */

  --border: oklch(1 0 0 / 10%);
  --input: oklch(1 0 0 / 15%);
  --ring: var(--palette-teal);

  --chart-1: var(--palette-terracotta);
  --chart-2: var(--palette-teal);
  --chart-3: var(--palette-tan);
  --chart-4: var(--palette-copper);
  --chart-5: var(--palette-stone);
}
```

`sidebar-*` tokens: not currently rendered anywhere in the app (no sidebar component exists
yet) — carry them forward mapped to the same values as `card`/`accent` for consistency, but
they're not a priority to hand-tune.

### Layer 3 — status tokens (new — fixes the two leaks from §1)

Status colors (success/warning/error/info) are a *semantic* system, intentionally kept
separate from the brand palette so usability signals (green = ok, amber = pending, red =
error) stay legible across brand palette swaps — but they still need to be CSS variables,
not inline Tailwind palette classes, so dark mode and future tuning stay centralized.

```css
:root {
  --success: oklch(0.6 0.13 145);
  --success-foreground: oklch(0.985 0 0);
  --warning: oklch(0.75 0.15 75);
  --warning-foreground: oklch(0.205 0 0);
  --info: var(--palette-teal);
  --info-foreground: oklch(0.985 0 0);
}
.dark {
  --success: oklch(0.7 0.15 145);
  --warning: oklch(0.8 0.15 75);
  --info: var(--palette-teal);
}
```

Add matching entries to the `@theme inline` block (`--color-success: var(--success)`, etc.)
so `bg-success`, `text-warning`, `border-info` become real Tailwind utilities.

Then fix the two leaks:

- `StatusDot.tsx`: `idle` → `bg-muted-foreground/40`, `ok` → `bg-success`, `warning` →
  `bg-warning`, `error` → `bg-destructive`; label text `text-zinc-500 dark:text-zinc-400` →
  `text-muted-foreground`.
- `ReportView.tsx`: `text-amber-500` → `text-warning`, `text-emerald-500` → `text-success`.

---

## 3. Migration steps

1. Add the Layer 1 `--palette-*` block to `globals.css`.
2. Replace the Layer 2 `:root`/`.dark` values with the table in §2 (values only — variable
   names and `@theme inline` mapping shape stay identical, so no component touches this).
3. Add the Layer 3 status tokens + `@theme inline` entries; fix `StatusDot.tsx` and
   `ReportView.tsx`.
4. Visual pass: run `mise run fe-start`, click through `/`, `/reports`, `/reports/new`,
   `/reports/[jobId]`, `/expert/reviews`, the new marketing landing page, and both themes
   (toggle via next-themes) — check button/card/badge states (hover, disabled, focus ring)
   and destructive/success/warning states in `ReportView`.
5. Contrast check: verify `primary`-on-`primary-foreground` and `accent`-on-`accent-foreground`
   meet WCAG AA in both themes (browser devtools contrast checker on the rendered button).
   The oklch lightness values above are a starting point, not guaranteed-AA — nudge `L` if
   a pairing fails.
6. `mise run "code:clean:fe"`.

No `orm_models.py`/backend changes, no new dependencies — this is a `globals.css` + two
component edits.

---

## 4. Making the *next* swap free (optional, do later)

If the palette needs to be swappable *at runtime* (a picker like the Coolors UI in the
reference image, not just "we changed brand once and edited the file"), the mechanism to
add is a second attribute alongside `next-themes`' `.dark` class:

- `services/tech/PaletteS.ts` — reads/writes `document.documentElement.dataset.palette` +
  persists to `localStorage` (infra adapter, no React).
- `services/business/usePalette.ts` — hook wrapping it for `ui/business/` consumers.
- `globals.css` gains `[data-palette="copper-aquamarine"] { --palette-*: ...; }` blocks
  alongside the current unscoped `:root` block (which becomes the default/fallback palette).

This is deliberately **not** part of this migration — do it only if a second palette is
actually needed. Building it now for a single palette would be the premature abstraction
the project's design conventions warn against.

---

## 5. Logo & icon marks

The logo concept was designed against this exact palette and was sitting in
`fe/ui/logo/WallRay Logo (standalone).html` — a bundled/exported artifact page, not
directly readable as markup (its `<script type="__bundler/template">` payload is a
JSON-escaped string, and one asset blob is a compressed font/JS bundle). Decoded the
template string and extracted the real SVG geometry below; it is now saved as six
plain, git-diffable `.svg` files in `fe/ui/logo/` instead of only existing inside the
opaque bundle.

**Concept — "Option 2a, scan reveals crack":** a wall panel (rounded rect) is swept by a
horizontal ray (the "Ray" of WallRay); a zigzag scan line travels down the panel and
branches into a small crack/chip shape it has just found. Three color roles, independent
of the container it sits on:

| Role | Shape(s) |
|---|---|
| **wall** | the rounded panel (`rect x=12 y=10 w=76 h=80 rx=6`) |
| **mark** | crack polygon + scan zigzag polyline + its connector segment |
| **ray** | the horizontal sweep at `y=55` — a soft-glow duplicate (`stroke-width 10`, `opacity ~0.3`) under a crisp core line (`stroke-width 3`) |

### Extracted files (`fe/ui/logo/`)

| File | Size | wall | mark | ray | Intended container |
|---|---|---|---|---|---|
| `wallray-lockup-88.svg` | 88px | `#30525C` deep teal | `#DCAA89` tan | `#C35627` copper | `#F6F3F1` card, wordmark below in `#30525C` |
| `wallray-icon-60.svg` | 60px | `#F6F3F1` cream | `#30525C` deep teal | `#C35627` copper | `#30525C` rounded-20px chip (app icon) |
| `wallray-favicon-22.svg` | 22px | `#F6F3F1` cream | `#30525C` deep teal | `#C35627` copper | `#30525C` rounded-6px 32px chip — connector line and ray glow dropped, strokes bolded, for legibility at favicon size |
| `wallray-mono-on-white-44.svg` | 44px | `#111` | `#fff` | `#fff` (glow `#111`) | plain white card |
| `wallray-mono-on-black-44.svg` | 44px | `#fff` | `#111` | `#111` (glow `#fff`) | plain black card |
| `wallray-lockup-dark-68.svg` | 68px | `#F6F3F1` cream | `#30525C` deep teal | `#D6794D` terracotta | `#20363E` dark card, wordmark below in `#F6F3F1` |

Note the **wall/mark pair always inverts** between light and dark containers (cream panel
with deep-teal mark on a dark chip; deep-teal panel with tan mark on a light card) — the
mark reads as a cutout of whatever it sits on. And note **ray recolors independently**:
copper (`--palette-copper`) on light/mid containers, terracotta (`--palette-terracotta`)
on the dark lockup — the same light/dark substitution already used for `--primary` in §2.

### Wiring the logo into the token system

The container-baked files above are for contexts that can't consume CSS variables
(favicons, OG images — browsers fetch these as static assets, no host-page styling
applies). For every **in-app** use (header, sign-in page, footer) the logo should instead
be a real inline component, `fe/ui/base/Logo.tsx`, rendering the same geometry as JSX
`<svg>` (not `<img src>`) so its three color roles resolve through new semantic tokens —
this is what actually makes the logo obey a palette swap instead of shipping frozen hex:

```css
:root {
  --logo-wall: var(--palette-deep-teal);
  --logo-mark: var(--palette-tan);
  --logo-ray: var(--palette-copper);
}
.dark {
  --logo-wall: oklch(0.94 0.006 60);   /* matches dark-mode --foreground cream */
  --logo-mark: var(--palette-deep-teal);
  --logo-ray: var(--palette-terracotta);
}
```

`Logo.tsx` then takes a `size` prop and fills the three shape groups from
`var(--logo-wall)` / `var(--logo-mark)` / `var(--logo-ray)` — one component, no
light/dark or per-palette branching in the component itself, matching the `bg-primary`
pattern used everywhere else. Not built as part of this plan — flagged here so it isn't
missed when `Logo.tsx` gets built.

### Favicon / app icon (static, still needs to ship)

Next.js reads `fe/app/icon.svg` / `fe/app/apple-icon.png` by convention; neither exists
yet (only the default `fe/app/favicon.ico`). `wallray-favicon-22.svg` and
`wallray-icon-60.svg` are the source marks for these — they still need their container
chip (the `#30525C` rounded square) baked into the file itself, since a favicon has no
host page to supply that background via CSS. A static SVG favicon *can* react to OS theme
without any host page, via a self-contained media query:

```xml
<style>
  @media (prefers-color-scheme: dark) { .wall { fill: #F6F3F1 } .mark { fill: #30525C } }
  @media (prefers-color-scheme: light) { .wall { fill: #30525C } .mark { fill: #F6F3F1 } }
</style>
```

This is a separate, small task (bake container + add the media query), not addressed by
this plan.
