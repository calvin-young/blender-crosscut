# Contributing

Thanks for your interest! Crosscut aims to be a general-purpose sectioning tool for Blender, and
it gets better when people with different workflows contribute.

## Ways to help

- **Report a bug or request a feature** in [Issues](../../issues). Include:
  - your Blender version, OS and GPU backend (OpenGL / Vulkan / Metal),
  - the viewport shading mode and Crosscut settings you used,
  - steps to reproduce and a screenshot,
  - a small synthetic example file if you can.
- **Pick up an issue** labeled `good first issue` or `help wanted`. Comment first so we don't
  duplicate work.
- **Built something in your fork?** We'd love to see it once it's finished. See "Submit once" below.

## Making a change

1. Fork the repo and create a branch from `main`.
2. Read [docs/DECISIONS.md](docs/DECISIONS.md) so you know what's been tried and why.
3. Match the existing style (see [AGENTS.md](AGENTS.md) for layout and conventions).
4. **Finish and validate in your fork.** Use the feature for real in Blender, fix the bugs you
   find, and run the tests (`python tests/test_section_math.py && python tests/test_addon_logic.py`).
   Your fork's history can be as messy as you like.
5. **Tidy up.** Organize the work into one PR per logical change, each with a clean history.
6. **Submit once.** Open the PR, or the whole set of PRs, together, and fill in the template.

Please don't send work-in-progress PRs followed by fix-up PRs as bugs turn up. A finished feature
reviewed once is much easier to evaluate than a moving one.

Planning something big? Feel free to open an issue first to check it fits.

## Using AI assistants

Welcome. Please:

- finish, test and debug the work in your fork before submitting, as above;
- run and test what your assistant produced yourself, in Blender;
- fill in the **Requested vs. assumed** section honestly. It's how reviewers tell what was
  intended from what was guessed.

## Data

Don't include real production data, customer or company names, or private file paths in issues,
tests or PRs. Use synthetic examples.

## License

By contributing, you agree that your contributions are licensed under GPL-3.0-or-later
(see [LICENSE](LICENSE)).
