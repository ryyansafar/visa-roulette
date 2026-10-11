# Design direction: Gate Board

The look is airport wayfinding and departure boards, not "AI landing page".
It grew out of a random seed (a 12x12 character block with a strong amber hue, a steel-blue and a
green run, and a lot of digits). The seed is not stored in the repo.

## Rules
- **Grid:** 12 columns, 12 px gutter. The globe takes 8 columns, the checklist 4. Break the grid on purpose
  for the stamp and the dart, nowhere else.
- **Colour:** ink-blue ground, signal yellow for the one thing that matters on screen, green = go,
  red = held, amber = review. One signal colour per screen. Paper (cream) only for flight-ticket surfaces.
- **Type:** Space Grotesk for display and UI, IBM Plex Mono for data (MRZ, rule ids, timestamps), Barrio only
  inside stamps. Tabular numerals everywhere. Labels are mono, small caps feel, wide tracking.
- **Numerals are the hero.** Big outcome numbers (score, months left, budget) at 96 px.
- **Shape:** hairline rules and square corners. Circles only for stamps. No shadows, no glass, no gradients.
- **Motion:** mechanical. Split-flap ticks (120 ms) when values change, a 380 ms thud for the stamp.
  The dart arc is the only long animation. Everything respects prefers-reduced-motion.
- **Globe:** treated as an instrument, not a glow. NASA day map with a hard night terminator and city lights,
  hairline graticule, country borders in rule colour, the landing spot marked in signal yellow.
- **Content first:** every number or verdict on screen links to its rule or source.

## Avoid
Purple-blue gradients, glassmorphism cards, emoji as icons, centred hero + subtitle + two buttons, rounded
everything, neon glow, stock illustration.

## Files
`web/styles/tokens.css` holds the tokens (dark by default; `data-theme="light"` or the OS preference switches to light).
`web/styles/polish.css` loads last and holds the design-critic overrides: flat stamps, the pre-throw route card
(Throw / Check / Prepare), the rail hiding mode controls after landing, and the light-theme yellow primary button.
Fonts and the NASA maps live in `assets/` (see credits in README). The review process is in `DESIGN_CRITIC_LOOP.md`.
