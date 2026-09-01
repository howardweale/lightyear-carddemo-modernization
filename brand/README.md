# LIGHTYEAR brand system

![LIGHTYEAR primary logo](assets/lightyear-primary.svg)

Version 1.0 applies the supplied logo system across the product UI, milestone website, generated Word/PDF briefs, and presentation templates.

## Core system

| Token | Value | Use |
|---|---|---|
| Deep navy | `#15184D` | Headlines, body ink, dark fields |
| Signal violet | `#7D57EA` | Logo mark, links, active and focus states |
| Bronze | `#A7702C` | Wordmark, rules, secondary emphasis |
| Paper | `#FEFEFE` | Primary backgrounds |
| Pale lavender | `#EFEBFB` | Secondary surfaces and subtle emphasis |

The primary tagline is **Where context becomes trusted action.** IBM Plex Sans and IBM Plex Mono are the product typefaces; Arial is the portable fallback for generated office files.

## Assets

- `lightyear-primary.svg`: primary wordmark across the icon.
- `lightyear-icon.svg`: icon-only mark.
- `lightyear-horizontal.svg`: preferred horizontal product/document lockup.
- `lightyear-reversed.svg`: reversed mark for deep navy fields.
- `lightyear-horizontal-reversed.svg`: horizontal lockup for dark fields.

PNG exports are generated from these SVG sources for Word, PDF, and PowerPoint compatibility.

## Usage

- Keep clear space on every side equal to at least the cap height of the wordmark.
- Do not stretch, rotate, recolor, outline, or add effects to a logo asset.
- Use the primary mark at no less than 24 mm in print and the icon at no less than 14 mm.
- Place the primary or horizontal mark on white or uncluttered pale surfaces.
- Use a reversed asset on deep navy backgrounds.
- Preserve semantic status colors (green, amber, red) for operational state; violet is the interaction and brand signal.

## Regeneration

```bash
./milestone-documentation.sh build
node tools/generate_brand_deck.mjs
```

The milestone builder regenerates Markdown, Word, PDF, and the searchable documentation website from the governed catalog. The deck generator creates `brand/Lightyear-Deck-Template.pptx`.

## Foundation decks

- [`foundation/LIGHTYEAR-Investor-Foundation.pptx`](foundation/LIGHTYEAR-Investor-Foundation.pptx): investor and VC narrative foundation.
- [`foundation/LIGHTYEAR-Developer-Architecture-Foundation.pptx`](foundation/LIGHTYEAR-Developer-Architecture-Foundation.pptx): developer and architecture narrative foundation.

Both foundations preserve their original slide systems and use the approved dark LIGHTYEAR lockup throughout.
