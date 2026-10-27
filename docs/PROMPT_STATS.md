# Collaboration log

How this project was made with AI help, and how much of it the human steered. It holds counts
and one-line summaries, never prompt text.

## Disclosure

- **Tools and models:** Claude (claude.ai cloud agent session, Claude Opus 5.5) for 0.1.0;
  Claude Code on a dedicated development machine from 2026-10-26.
- **How much is AI:** almost all. The AI writes the code, tests and docs and runs the tests; the
  maintainer reviews little of the code.
- **What the human did:** set the requirements (with hand-made reference mock-ups), chose the
  name, tests each build in Blender on real work and reports back, and polices the interface.
- **How AI work is marked:** commits made by the AI end with `Co-Authored-By: Claude <model>` and
  a session link (ai-context WORKING_STYLE, section 6).
- **Accountability:** the maintainer publishes and answers for everything in the repository.

## Sessions

One row per working session. Prompts are counted by hand in chat apps and with
`tools/prompt_stats.py` from the ai-context repo on Claude Code transcripts. The count of
steering lines matters more than the count of prompts.

| Date | Tool and model | Prompts | Steering lines | Notes |
|---|---|---|---|---|
| 2026-10-26 | Claude (cloud session), Opus 5.5 | 1 | 3 | Repo created; first user test; handoff to Claude Code |
| 2026-10-22 | Claude (cloud session), Opus 5.5 | 1 | 6 | Initial spec with 3 mock-ups; 0.1.0 built without Blender access |

## Steering

One line for each thing the human contributed that the AI would not have done on its own,
newest first, tagged with its kind (decide, correct, domain, tested, scope).

- 2026-10-26 [scope]: move development to the dedicated machine; next build must be run and tested in Blender before he gives detailed feedback.
- 2026-10-26 [tested]: first try in Blender: looks great, definitely buggy.
- 2026-10-26 [decide]: created the repo as blender-crosscut, accepting the name.
- 2026-10-22 [scope]: standalone add-on first, then compare the experience tied to bucket dimensions.
- 2026-10-22 [domain]: Netfabb has scrubbable clipping; useful across the build volume and for finding interferences when packing.
- 2026-10-22 [decide]: overlapping bodies must be handled; comparing sections of several parts is a common need.
- 2026-10-22 [decide]: slice-only view to replace the thin-box boolean intersect workaround (mock-up supplied).
- 2026-10-22 [decide]: toggle between native backfaces and a solid CAD-style section (Creo Direct as reference; mock-ups supplied).
- 2026-10-22 [domain]: uses Alt+B constantly while modelling; fakes sections today with booleans and hand-drawn hatching.

The requested-vs-assumed tally is in [DECISIONS.md](DECISIONS.md).
