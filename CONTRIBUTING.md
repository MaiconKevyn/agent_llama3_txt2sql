# Contributing to DataVisSUS TXT2SQL Agent

## Commit messages — Conventional Commits

This project follows the [Conventional Commits](https://www.conventionalcommits.org/) specification.
Every commit message must match the pattern:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Allowed types

| Type       | Use for |
|------------|---------|
| `feat`     | New feature or capability |
| `fix`      | Bug fix |
| `perf`     | Performance improvement |
| `refactor` | Code change that is neither a fix nor a feature |
| `eval`     | Changes to evaluation scripts, benchmarks, or results |
| `prompt`   | Changes to prompts, RULES, or few-shot examples |
| `docs`     | Documentation only |
| `test`     | Adding or fixing tests |
| `chore`    | Build system, dependencies, tooling |
| `ci`       | CI/CD pipeline changes |
| `style`    | Formatting, whitespace (no logic change) |
| `build`    | Build system or external dependencies |

### Breaking changes

Append `!` before the colon to signal a breaking change:

```
feat!: redesign table selection API
```

Or add `BREAKING CHANGE:` in the footer.

### Scope (optional)

Use a short noun describing the affected area:
`classification`, `sql_generation`, `workflow`, `evaluation`, `table_selection`, `state`, `api`, `config`, `prompts`

### Examples

```
feat(classification): add heuristic fast-path for DATABASE queries
fix(execution): move get_llm_manager call after SQL safety check
eval(ablation): add CP-A1 ablation matrix runner
prompt(rules): update RULE H for DuckDB NULL semantics
chore(deps): bump langchain-core to 0.3.74
docs(readme): add uv setup instructions
refactor(state): extract state_models and state_helpers from state.py
```

### Changelog generation

The `CHANGELOG.md` is generated automatically from commit history via `git-cliff`:

```bash
# Preview unreleased changes
git-cliff --unreleased

# Regenerate full changelog and write to file
git-cliff -o CHANGELOG.md

# Generate for a specific tag range
git-cliff v0.2.0..v0.3.0 -o CHANGELOG.md
```

The hook in `.githooks/commit-msg` validates the format locally on every commit.
Git is configured to use it via `core.hooksPath = .githooks` (already set in `.git/config`).
New contributors must run:

```bash
git config core.hooksPath .githooks
```

## Semantic versioning

This project uses [SemVer](https://semver.org/). Tags follow `vMAJOR.MINOR.PATCH`.

- `PATCH` — bug fixes, docs, chores
- `MINOR` — new features, eval improvements, accuracy gains
- `MAJOR` — breaking API changes or major architecture redesign

Current baseline: **v0.3.0** — EX = 93.3 % on 120-query benchmark.
