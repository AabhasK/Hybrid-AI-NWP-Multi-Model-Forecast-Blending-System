# Prompt for the slide-building agent

Copy everything inside the box below into Claude Design (or Claude Code) as the
task. It is written to stop the three things that make generated decks look
generated: invented numbers, decorative filler, and interchangeable layouts.

---

````text
You are building the Smart India Hackathon idea-submission deck for team
Stash&Rebase, problem statement SIH26081, "Hybrid AI–NWP Multi-Model Forecast
Blending System" (Ministry of Earth Sciences / NCMRWF, theme: Disaster
Management). The audience is NCMRWF meteorologists. They know weather models
better than you do and will notice anything vague, inflated or wrong.

READ THESE FIRST, IN ORDER, BEFORE WRITING ANYTHING:
  1. docs/PPT_BRIEF.md       - slide-by-slide content, numbers, design system
  2. docs/PS_COMPLIANCE.md   - what we meet, what we don't, and why
  3. docs/DASHBOARD_GUIDE.md - what each screenshot shows
  4. docs/assets/            - screenshots of the real product, 1920x1080

======================================================================
NUMBERS
======================================================================
- Use ONLY numbers that appear in docs/PPT_BRIEF.md or docs/PS_COMPLIANCE.md.
  Copy them exactly. Do not round, restate, average or "approximately" them.
- If a slide seems to need a number that is not in those files, leave a visible
  placeholder "[NUMBER NEEDED: <what>]". Never estimate one.
- Never write "up to", "over", "nearly", "significantly", "dramatically" in
  front of a number, or instead of one.
- Every results claim must name what it is compared against. "29% less error"
  alone is meaningless; "29% less error than ECMWF IFS" is a claim.
- Respect the "Do not claim" list in PPT_BRIEF.md literally.

======================================================================
WORDS
======================================================================
Banned outright - do not use these words or their variants:
  revolutionise, transform, cutting-edge, state-of-the-art, next-generation,
  seamless, robust, leverage, empower, unlock, harness, game-changer,
  innovative, intelligent (as praise), powerful, comprehensive, holistic,
  synergy, paradigm, journey, landscape, ecosystem, delve, elevate, streamline

- Slide titles are full sentences that state the point, not topic labels.
    Bad:  "Our Solution"          Good: "Blend Desk learns which model to trust, where and when"
    Bad:  "Results"               Good: "The blend beats every single model it combines"
- Write for a meteorologist: say "ECMWF IFS", not "a leading global model".
- Expand every acronym once: ECMWF AIFS = Artificial Intelligence Forecasting
  System. Say "five model streams from four centres", never "five centres".
- No rhetorical questions as titles. No exclamation marks. No emoji.

======================================================================
VISUALS
======================================================================
- The product screenshots ARE the visuals. Use them instead of icons,
  illustrations or stock imagery. Do not draw a fake chart or mock UI.
- CROP screenshots to the part that makes the point. A full 1920x1080 page
  shrunk into a slide makes every label unreadable.
- Strongest image: docs/assets/03a-cell-rainfall.png and 03b-cell-temperature.png
  SIDE BY SIDE. Same place, same day - the donut flips from orange (ECMWF AIFS)
  to blue (ECMWF IFS). It answers "why not just use the AI model?" on sight.
- No icons next to bullet points. No three-column "feature" grids with an icon
  above each column. No gradient blobs, glows, particles or abstract waves.
- No glass/frosted panels, no drop shadows, no rounded cards added for
  decoration. Keep slide furniture flat and quiet.

======================================================================
DESIGN SYSTEM - match the product exactly
======================================================================
- Font: Inter only (400/500/600/700). Vary weight, not typeface.
- Background #263749 · panels #33465b · rules #52657a
- Text #f3f4ff primary · #c1ccd7 secondary · #a0afbd tertiary
- Accent #ffd426 - ONE element per slide at most. Two yellow things = none.
- Model colours are a fixed key used on every chart. Never swap or restyle:
    ECMWF IFS #3987e5 · ECMWF AIFS #d95926 · NOAA GFS #199e70
    DWD ICON #9085e9  · EC GEM #c98500     · Persistence #64788c
- Body text at least 18pt. It must read on a projector from the back of a room.
- Tabular (monospaced) figures for any number in a table.
- Left-align text. Do not centre paragraphs.

======================================================================
STRUCTURE
======================================================================
- Follow the current SIH idea-submission template's slide count and headings.
  If you cannot see the template, stop and ask for it. Exceeding the slide
  count gets a submission rejected.
- One idea per slide. If a slide needs two headings, it is two slides.
- Vary the layout by what each slide has to show - a comparison is two columns,
  a result is one big number with its comparison, a process is a flow. Do not
  apply the same template to every slide.
- At most 5 bullets on a slide, at most 12 words each.
- Include the honest limitations slide content from PS_COMPLIANCE.md section 6.
  Volunteering weaknesses is a strength with this audience; hiding them is not.

======================================================================
BEFORE YOU HAND IT BACK
======================================================================
Check every slide and fix anything that fails:
  [ ] Every number traced to PPT_BRIEF.md or PS_COMPLIANCE.md, copied exactly
  [ ] No banned word anywhere, including speaker notes
  [ ] Every title is a sentence that states a claim
  [ ] Every screenshot cropped so its labels are readable
  [ ] No icons, gradients, glass effects or emoji
  [ ] Accent colour used at most once per slide
  [ ] Model colours match the fixed key
  [ ] Slide count within the SIH template
Then list, separately, every place you left a [NUMBER NEEDED] placeholder.
````

---

## Why each rule is there

| Rule | The failure it prevents |
|---|---|
| Numbers only from two named files | A deck that says "40% better" when the product says 29% — the fastest way to lose an expert panel |
| Placeholder instead of estimate | The agent filling a gap with a plausible-sounding figure |
| Banned vocabulary | The single strongest tell that nobody edited the deck |
| Titles as claims | A slide titled "Results" makes the judge do the work of finding the point |
| Screenshots, no icons | Icon grids signal "template"; real screenshots signal "we built it" |
| Crop, don't shrink | Unreadable 1920px screenshots scaled to a third of a slide |
| One accent per slide | Emphasis that is everywhere is emphasis nowhere |
| Fixed model colours | Judges learn orange = AIFS on slide 3 and are misled if it changes on slide 5 |
| Include the limitations | This audience finds the weaknesses anyway; saying them first is the credible move |
