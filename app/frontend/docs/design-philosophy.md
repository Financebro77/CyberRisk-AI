# Night Ledger

_A design philosophy for the CyberRisk AI frontend._

---

## The movement

A dark quantitative system built for the people who sign the risk. It is the
terminal of a loss-ledger clerk working the night shift — a discipline born in
the ship-chandlers' coffee houses where underwriters first gambled on the sea,
now applied to the ocean of the network. Every screen is a page in that ledger:
figures recorded in monospaced precision, the shape of rare disaster drawn
honestly, and the space around each number treated as information.

## Space and form

Surfaces are deep navy, stacked in hairline-edged strata: page, card, inset
field. Each layer reads instantly by its elevation. Form is quiet, rectilinear,
architectural — the geometry of actuarial tables and board-pack annexes, not
marketing gradients. Rounded corners are modest, shadows are faint, borders are
hairlines.

## Color and material

One signal color only: **cyan**, the color of phosphor and of a terminal
cursor — used for the things that mean "you are here, act here." Green, amber,
and red are the moral language of risk: they appear only where a number says
something about severity. The palette is otherwise monochrome navy and slate, so
a single accent never has to compete.

## Scale and rhythm

Numbers are the heroes. Monetary and probability figures are set in a tabular
monospace that declares their honesty — each digit the same width, nothing to
hide. Display type is the serif of the consulting report, used with restraint
for the sentences that frame the numbers. Rhythm comes from the vertical stack
of sections, each a clean ledger row.

## Composition and hierarchy

The single most important number on any page is the largest and quietest: a big
score, a big expected loss, a big tail figure. Supporting figures shrink in
orderly tiers. The loss curve — the distribution's tail — is drawn as a patient
line: most years flat, then the rare steep fall, marked at 1-in-100 and
1-in-1000 like reference ticks on a scientific instrument.

## Craft

This is the product of a master of both crafts: actuarial rigor and typographic
discipline. Every alignment is a measurement, every tick mark placed with
painstaking attention, every gray chosen to sit exactly one step off its
neighbor. It must read as though countless hours went into the ledger's ruling —
because the one thing a risk advisory can never be is careless.

---

## Orientation to this brief (code mapping)

- **Deep navy strata** — `ink-*` scale already flips via `.dark`; cards get one
  elevated navy step (`#111a2e`) above the page (`#0b1220`).
- **Cyan phosphor** — `brand-*` redefined to a cyan scale; a single
  `--color-accent` flips between cyan-700 (light) and cyan-400 (dark) for
  eyebrows and highlights. Risk tones brightened in dark for legibility.
- **Tabular monospace heroes** — KPI values set in JetBrains Mono (`font-mono`),
  tabular numerals; serif Newsreader retained for advisory sentences.
- **The tail curve** — an inline SVG loss distribution on the landing hero,
  cyan stroke, tail shaded, hairline markers at 1-in-100 and 1-in-1000.
- **Hairline discipline** — `@layer components` so utilities can override
  shared classes; no unlayered styles fighting the design.
