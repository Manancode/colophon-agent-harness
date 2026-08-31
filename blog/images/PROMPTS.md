# chatgpt image-generation prompts for the blog

generate these with chatgpt (or any image model), then send the images back.
drop them in this `blog/images/` folder and tell me, and i will swap them into
the post and redeploy. filenames i expect: `hero.png`, `pipeline.png`,
`inside-trueforge.png`.

general rules baked into every prompt (to avoid "ai slop"):
- flat editorial vector, thin uniform lines, white background
- no gradients, no glow, no neon, no 3d render, no drop shadow, no stock-photo realism
- limited palette: black ink (#1c1c1e) plus at most ONE muted accent (#0b7e8e)
- if the model puts readable words in the image and they look wrong, that is fine,
  we keep the real labels in the html caption, not the image

---

## prompt 1 — hero / opening banner (optional but high impact)

> editorial concept illustration for a developer blog post about deterministic
> video quality assurance. subject: a calm, minimal scene suggesting an
> "instrument" checking a video, not a person. style: flat vector, thin uniform
> 1.5px ink-black lines (#1c1c1e) on pure white background, no fills or only very
> light grey (#f2f3f5), zero gradients, zero glow, zero neon, no 3d, no drop
> shadows, no stock-photo realism. limited palette: black ink plus a single muted
> desaturated teal (#0b7e8e) used sparingly for one accent. composition: a simple
> rectangular "video frame" on the left with a few abstract motion ticks, and a
> small gauge or checklist on the right connected by a thin arrow, implying
> measurement. no readable words in the image (any text should be abstract ticks
> or a single checkmark, not letters). aspect ratio 3:1 wide banner, 1500x500px.
> reference aesthetic: anthropic research blog diagrams and printed engineering
> manuals, utilitarian, precise, confident, human, never decorative.

## prompt 2 — the pipeline figure (replaces fig 1)

> clean technical pipeline diagram for a blog, flat vector on white. six
> sequential rounded rectangles left to right connected by thin arrows: (1) brief
> and brand, (2) canonical spec, (3) editable project, (4) render, (5)
> deterministic qa, (6) review and repair. thin 1.5px black (#1c1c1e) strokes,
> white fills, no colour except one rectangle outlined in muted teal (#0b7e8e).
> minimal or no text inside boxes, use simple icons: a document, a list, a film
> frame, a play triangle, a shield, a pencil. thin arrows between boxes. small
> caption line under the diagram in muted grey: "every gate fails closed". no
> gradients, no glow, no 3d, flat editorial style like an anthropic engineering
> post. aspect ratio about 3.3:1, 1200x360px.

## prompt 3 — colophon inside trueforge (replaces fig 2)

> architecture diagram for a blog, flat vector on white. a large rounded rectangle
> representing an "agent harness", containing three smaller rounded rectangles in
> a row: "agent", "validate tool", and "verdict", connected by thin arrows, with a
> dashed return arrow from verdict back to agent. thin 1.5px black strokes, white
> fills, one muted teal accent on the validate box. a few small monospace-style
> ticks at the bottom suggesting other tools. no gradients, no glow, no 3d, flat
> precise editorial style like an anthropic research diagram. aspect ratio about
> 2.6:1, 1200x460px.
