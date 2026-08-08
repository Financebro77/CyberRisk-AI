# Screenshots & diagrams

This directory is reserved for the images referenced in the main
[`README.md`](../../README.md). The images do not exist yet — the README
links to them as placeholders so the screenshots can be added without any
other changes.

> **Do not commit generated or fake images.** Add real screenshots from an
> actual run only.

## Expected files

| File | Purpose | Referenced in |
|---|---|---|
| `landing.png` | Landing page screenshot (the web app at `http://localhost:8000`) | README header / "Web Application Usage" |
| `risk-assessment-output.png` | Risk assessment output screenshot (a worked assessment) | README "Example Cyber Risk Assessment" |
| `architecture.png` | Architecture diagram (engine → simulation → metrics → agent) | README "Architecture" |

## How to capture them

1. **Landing** — run the app (Docker or `uvicorn`), open `http://localhost:8000`, screenshot the landing page.
2. **Risk assessment** — run an example (e.g. `python examples/run_full_pipeline.py` or the web app) and screenshot the risk-assessment output.
3. **Architecture** — render the architecture diagram (e.g. draw it from the ASCII diagram in the README / `docs/architecture.md`) and export to PNG.

## Notes

- Keep images reasonably sized (< 1 MB each) so the repo stays light.
- PNG preferred (crisp on light and dark GitHub themes).
- Name files exactly as above so the README links resolve without edits.
