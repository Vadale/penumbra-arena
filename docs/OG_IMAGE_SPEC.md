# Open Graph image spec (docs/og.png)

The OG image is what social media + LinkedIn + Twitter previews
show when someone shares the GitHub URL. It must convey the
project's identity and one striking visual element.

## Required content

A single, dense 1200 × 630 PNG.

Left third (400 × 630):
- "PENUMBRA" wordmark in a heavy mono typeface (e.g. JetBrains Mono
  Black) — cyan on near-black background.
- Subtitle: "privacy-preserving perpetual multi-agent arena"
- One-liner: "teach + benchmark + dataset · MIT + CC-BY-4.0"
- Github URL: `github.com/Vadale/penumbra-arena`

Right two thirds (800 × 630):
- A representative composition of the dashboard. Best choices:
  - The 3D arena view with fuzzy clouds (cropped square)
  - Plus a strip of 4 analytics tiles below (PCA, Bayesian
    posterior density, persistence barcode, monte carlo fan)
- Tint with the project's cyan/ember palette.

## Design constraints

- **Resolution**: exactly 1200 × 630. This is the OG-image standard.
- **File size**: < 600 KB (Twitter/X reject larger).
- **Background**: near-black (#0a0a0f) so it stands out in feeds.
- **Typography**: monospaced for the wordmark; UI font for the
  subtitle.
- **Contrast**: text must remain readable at 600 × 315 (the
  Twitter timeline thumbnail size).
- **No QR codes, no logos of third parties.**

## How to generate

Option A — Figma / Sketch / Affinity (recommended):
1. New artboard 1200 × 630.
2. Paste hero screenshot at 70% width, right-aligned.
3. Add text layer per spec above.
4. Export PNG at 1x.

Option B — programmatic (Pillow / SVG → PNG):
1. Render the dashboard via headless Chrome to a 800 × 630 PNG.
2. Compose with the text overlay using `pillow` or `imagemagick`.

## File path

Save as `docs/og.png`. Reference it in `apps/web/index.html` head:

```html
<meta property="og:image" content="https://raw.githubusercontent.com/Vadale/penumbra-arena/main/docs/og.png" />
<meta name="twitter:image" content="https://raw.githubusercontent.com/Vadale/penumbra-arena/main/docs/og.png" />
```

## Status

(Maintainer: complete before the OSS launch announcement. Track in
OSS_LAUNCH_ROADMAP.md week 3 deliverables.)
