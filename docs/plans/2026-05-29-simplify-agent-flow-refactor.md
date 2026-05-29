# Refactor Plan: Simplify Agent Flow Without Overfitting

Date: 2026-05-29
Branch: `refactor/simplify-agent-flow`
Status: Draft for implementation

## Objective

Simplify the Text-to-SQL agent so the production path keeps only components with measurable impact on correctness, latency, cost, or safety. The refactor must reduce rule sprawl and test overfitting while preserving the scientific evaluation discipline needed to decide which parts of the LangGraph architecture are actually useful.

Target flow:

```text
NL query
-> Intent/Plan parser
-> SemanticPlan
-> lightweight PlanAuditor
-> SQLStrategyRouter
-> SQLValidator
-> execute
-> response

On validator/execute failure only:
-> ErrorClassifier
-> TargetedSQLRepair
-> SQLValidator
-> execute
-> response
```

## Current Evidence

The latest reviewed ablation run was:

`evaluation/ablation/results/ablation_20260529T004837`

Important signals:

- `V0/full_pipeline`: EX `0.3000`, avg latency `21.15s`, total cost `$0.169378`.
- `V2/no_cot_reasoning`: EX `0.3000`, avg latency `15.737s`, total cost `$0.160816`.
- `V4/no_repair`: EX `0.2889`, avg latency `13.192s`, total cost `$0.106508`.
- `V7/no_rules`: EX `0.2889`, avg latency `18.258s`, total cost `$0.152226`.
- `V10/no_semantic_plan_validation`: EX `0.3444`, avg latency `19.384s`, total cost `$0.145851`.
- `LI2/llamaindex_sql_draft`: EX `0.3000`, avg latency `17.815s`, total cost `$0.056384`.

Interpretation:

- CoT reasoning is not justified as a default component on this run.
- SemanticPlan validation currently has false-positive or misplanned blocking behavior.
- Repair has small EX contribution in this run and should become targeted, not broad.
- Rules A-O may have value, but the current monolithic prompt block is not scientifically isolated enough.
- The dataset is failure-enriched and should not be used alone as production performance evidence.

## Non-Goals

- Do not rewrite the whole agent in one pass.
- Do not remove LangGraph only because it is complex; evaluate each node by evidence.
- Do not tune to specific GT IDs or benchmark questions.
- Do not delete existing user changes or generated result artifacts as part of this branch unless explicitly scoped later.
- Do not change gold SQL to fit the agent behavior.

## Architecture Decisions

- `SemanticPlan` remains the canonical contract between planning, generation, validation, and response.
- Rules must be typed, discoverable, and ablatable. Anonymous prompt text and hidden conditionals are not acceptable long-term.
- Validators are split into blocking invariants and non-blocking guidance.
- Repair remains in the architecture, but only as an error-triggered branch with a small retry budget.
- Deterministic SQL is allowed only through a registry with declared family, confidence, and test coverage.
- Evaluation decisions must be paired by query and reported with EX, semantic validity, workflow success, cost, tokens, and latency.

## Component Policy

### Keep By Default

- Query classification and answerability checks.
- Table/schema retrieval.
- `SemanticPlan` schema and typed plan rendering.
- Clinical concept catalog for known CID concepts.
- SQL validity checks.
- Execution result comparison and cost/token/latency tracking.
- Targeted repair for SQL/schema/high-confidence contract failures.

### Disable Or Demote By Default Unless Re-Justified

- CoT reasoning before SQL generation.
- Monolithic RULES A-O prompt block.
- Legacy `check_semantic_rules` hard-coded repair messages.
- Blocking SemanticPlan validation for low-confidence planner outputs.
- Broad semantic repair guidance that rewrites intent instead of fixing SQL.
- Deterministic macros that do not declare coverage and confidence.

## Scientific Acceptance Criteria

A component/rule is kept in the default path only if at least one condition is true:

- It improves paired EX on holdout by at least 2 percentage points with no material cost/latency regression.
- It reduces a known high-impact failure family by at least 10 percent relative error on a family-specific set.
- It prevents high-severity invalid SQL or unsafe execution behavior.
- It improves cost or latency by at least 10 percent with no EX loss.

A component/rule is removed, disabled, or demoted if:

- Paired EX delta is near zero and cost/latency increases.
- It has repeated false positives in validation.
- It only passes benchmark examples by matching phrasing.
- It duplicates another layer's responsibility.

## Test Tiers

Use the smallest useful tier after each checkpoint, then broaden before merging.

### Tier 0: Static And Import Checks

```powershell
uv run ruff check src evaluation tests
uv run python -m compileall src evaluation tests
```

### Tier 1: Focused Unit Tests

```powershell
uv run pytest tests/test_semantic_layer.py
uv run pytest tests/test_sql_execution_block.py
uv run pytest tests/test_semantic_validators.py
uv run pytest tests/test_routing.py
uv run pytest tests/test_evaluation_result_matching.py
```

### Tier 2: Focused Regression Smoke

```powershell
uv run python -m evaluation.runners.run_regression --max-queries 10
```

### Tier 3: Targeted Ablation Smoke

```powershell
uv run python -m evaluation.runners.run_ablation `
  --variants V0 V2 V4 V7 V10 LI2 `
  --max-queries 15 `
  --workers 2
```

### Tier 4: Decision Ablation

```powershell
uv run python -m evaluation.runners.run_ablation `
  --variants V0 V2 V4 V7 V10 LI2 `
  --workers 2
```

### Tier 5: Generalization Evidence

```powershell
uv run python -m evaluation.agent.run_generalization_exhaustion --limit 30
```

Use live evaluation only when API keys, DB, and expected cost are available.

## Checkpoint 0: Branch And Baseline Hygiene

Goal: make the refactor branch safe to work on and define baseline evidence without changing behavior.

### Tasks

#### Task 0.1: Record dirty-worktree baseline

Description: capture current branch, dirty files, and known unrelated changes before implementation starts.

Acceptance criteria:

- [ ] Branch is `refactor/simplify-agent-flow`.
- [ ] Dirty worktree state is documented in implementation notes.
- [ ] No unrelated deletions or result artifacts are reverted.

Verification:

```powershell
git branch --show-current
git status --short
```

Files likely touched:

- `docs/plans/2026-05-29-simplify-agent-flow-refactor.md`

Dependencies: none.

#### Task 0.2: Create baseline metrics snapshot

Description: add a small Markdown or JSON summary of the latest ablation run so later checkpoints compare against the same evidence.

Acceptance criteria:

- [ ] Baseline includes EX, workflow success, cost, total tokens, avg latency, and p95 latency by variant.
- [ ] Baseline marks the dataset as failure-enriched.
- [ ] Baseline records the source directory and git SHA from the run.

Verification:

```powershell
Import-Csv evaluation\ablation\results\ablation_20260529T004837\results.csv |
  Select-Object variant_id,variant_name,ex_overall,avg_latency_s,p95_latency_s,total_tokens,total_cost_usd |
  Format-Table -AutoSize
```

Files likely touched:

- `docs/generated/ablation_baseline_20260529.md`

Dependencies: Task 0.1.

### Checkpoint 0 Verification

```powershell
git diff -- docs/plans docs/generated
uv run python -m compileall src evaluation tests
```

Stop if compile fails before any implementation.

## Checkpoint 1: Rule Inventory And Ownership

Goal: make every rule surface visible before deleting or moving anything.

### Tasks

#### Task 1.1: Build rule inventory schema

Description: define a structured registry for rules and constraints.

Acceptance criteria:

- [ ] Each rule has `rule_id`, `layer`, `family`, `severity`, `default_action`, `evidence`, `ablation_flag`, and `owner_module`.
- [ ] Registry distinguishes blocking invariants from prompt hints and soft guidance.
- [ ] Registry can represent existing prompt rules A-O, planner constraints, validator checks, and deterministic macros.

Verification:

```powershell
uv run pytest tests/test_semantic_layer.py -q
```

Files likely touched:

- `src/semantic/rule_registry.py`
- `src/semantic/rule_registry.yml`
- `tests/test_rule_registry.py`

Dependencies: Checkpoint 0.

#### Task 1.2: Inventory existing rule surfaces

Description: map the current rule sources without changing behavior.

Acceptance criteria:

- [ ] Inventory covers `prompt_builder.py`, `validation.py`, `semantic/validators.py`, `semantic/planner.py`, `schema_node.py`, and deterministic SQL macros.
- [ ] Each RULE A-O item maps to a rule ID.
- [ ] Known problematic families are tagged: CID lookup, top-N scope, rate denominator, UTI marker, unsupported schema, geography joins.

Verification:

```powershell
uv run pytest tests/test_rule_registry.py
uv run pytest tests/test_agent_improvements.py
```

Files likely touched:

- `docs/generated/rule_inventory.md`
- `src/semantic/rule_registry.yml`
- `tests/test_rule_registry.py`

Dependencies: Task 1.1.

### Checkpoint 1 Verification

```powershell
uv run ruff check src tests
uv run pytest tests/test_rule_registry.py tests/test_agent_improvements.py
```

Decision gate:

- No behavior change expected.
- If tests fail, inventory code is too coupled and should be simplified before proceeding.

## Checkpoint 2: Evaluation Harness For Decisions

Goal: make keep/remove decisions statistically and operationally defensible.

### Tasks

#### Task 2.1: Add component decision report

Description: extend ablation reporting to output paired deltas by family, cost, tokens, latency, and McNemar stats in one decision table.

Acceptance criteria:

- [ ] Report includes query-level paired comparison against V0.
- [ ] Report includes per-difficulty and per-family breakdown when metadata exists.
- [ ] Report flags variants that dominate V0 on cost/latency without EX loss.
- [ ] Report marks non-significant results as inconclusive, not as proof.

Verification:

```powershell
uv run pytest tests/test_ablation_decision_report.py
```

Files likely touched:

- `evaluation/runners/run_ablation.py`
- `evaluation/ablation/decision_report.py`
- `tests/test_ablation_decision_report.py`

Dependencies: Checkpoint 1.

#### Task 2.2: Add result artifact policy

Description: separate canonical datasets/reports from generated run outputs.

Acceptance criteria:

- [ ] Generated `evaluation/**/results/**` outputs are documented as artifacts.
- [ ] New runs are written to ignored artifact directories unless explicitly promoted.
- [ ] Canonical small reports remain tracked.

Verification:

```powershell
git status --short
git check-ignore -v evaluation/ablation/results/example.tmp
```

Files likely touched:

- `.gitignore`
- `evaluation/ablation/results/.gitignore`
- `docs/adrs/ADR-007-evaluation-artifact-policy.md`

Dependencies: Task 2.1.

### Checkpoint 2 Verification

```powershell
uv run pytest tests/test_ablation_decision_report.py tests/test_evaluation_result_matching.py
uv run python -m evaluation.runners.run_ablation --variants V0 V2 V10 --max-queries 6 --workers 2
```

Decision gate:

- Do not remove components until this report can compare them reproducibly.

## Checkpoint 3: Clinical Concept And CID Generalization First

Goal: fix the main known failure family without adding benchmark-specific rules.

### Tasks

#### Task 3.1: Make clinical concept resolution the default for known diseases

Description: route known clinical concepts to curated codes/prefixes before description lookup.

Acceptance criteria:

- [ ] "infarto agudo do miocardio" resolves to `I21%`.
- [ ] "pneumonia" resolves to the curated prefix/code policy already in the concept catalog.
- [ ] Description lookup remains available only as fallback for unknown concepts.
- [ ] SemanticPlan records resolution strategy and confidence.

Verification:

```powershell
uv run pytest tests/test_clinical_concepts.py
uv run pytest tests/test_semantic_layer.py -k "clinical or cid or infarto or pneumonia"
```

Files likely touched:

- `src/semantic/concept_resolver.py`
- `src/semantic/domain_resolvers.py`
- `src/semantic/planner.py`
- `tests/test_clinical_concepts.py`
- `tests/test_semantic_layer.py`

Dependencies: Checkpoint 2.

#### Task 3.2: Demote prompt rule "Filtering by named disease -> DESCRICAO ILIKE"

Description: replace the broad prompt instruction with a general policy: use curated concepts first, description lookup second, and expose uncertainty.

Acceptance criteria:

- [ ] Prompt no longer says named disease should always use `cid.DESCRICAO ILIKE`.
- [ ] Prompt tells the generator to preserve resolved CID filters from `SemanticPlan`.
- [ ] Unknown clinical names still get a safe lookup path.

Verification:

```powershell
uv run pytest tests/test_semantic_layer.py -k "cid or diagnosis"
uv run pytest tests/test_sql_execution_block.py -k "diagnosis or cid"
```

Files likely touched:

- `src/agent/prompt_builder.py`
- `src/semantic/catalog.yml`
- `tests/test_semantic_layer.py`

Dependencies: Task 3.1.

#### Task 3.3: Add CID family regression checks

Description: add family-level tests that prevent the old description-lookup overuse without tying to one GT ID.

Acceptance criteria:

- [ ] Tests include paraphrases of infarto, pneumonia, diabetes, broad cardiovascular/respiratory concepts.
- [ ] Tests include an unknown disease fallback case.
- [ ] Tests assert semantic filters and strategy, not exact full SQL strings.

Verification:

```powershell
uv run pytest tests/test_clinical_concepts.py tests/test_semantic_layer.py -k "cid or clinical"
```

Files likely touched:

- `tests/test_clinical_concepts.py`
- `tests/test_semantic_layer.py`

Dependencies: Task 3.2.

### Checkpoint 3 Verification

```powershell
uv run pytest tests/test_clinical_concepts.py
uv run pytest tests/test_semantic_layer.py -k "cid or clinical or diagnosis"
uv run python -m evaluation.runners.run_ablation --variants V0 V10 --max-queries 15 --workers 2
```

Decision gate:

- CID failures should decrease without adding GT-specific conditionals.

## Checkpoint 4: Split Planner Into Resolvers

Goal: reduce `semantic/planner.py` from a monolith into composable, testable units.

### Tasks

#### Task 4.1: Extract intent and answer-shape resolution

Description: move intent/top-N/row-grain logic behind a small resolver API.

Acceptance criteria:

- [ ] Public `build_semantic_plan()` output remains compatible.
- [ ] Intent resolver has focused tests for count, ranking, distribution, rate, trend, association, lookup, unknown.
- [ ] Top-N scope tests cover scalar false positives like "valor maior que zero".

Verification:

```powershell
uv run pytest tests/test_semantic_layer.py -k "intent or top_n or row_grain"
```

Files likely touched:

- `src/semantic/planner.py`
- `src/semantic/intent_resolver.py`
- `src/semantic/answer_shape_resolver.py`
- `tests/test_semantic_layer.py`

Dependencies: Checkpoint 3.

#### Task 4.2: Extract metric, dimension, and filter resolution

Description: isolate domain matching into metric, dimension, and filter resolvers.

Acceptance criteria:

- [ ] Each resolver returns typed candidates with confidence/source.
- [ ] Resolver output can be inspected in tests.
- [ ] Existing `SemanticPlan` model remains unchanged or changes only with migration tests.

Verification:

```powershell
uv run pytest tests/test_semantic_layer.py
```

Files likely touched:

- `src/semantic/metric_resolver.py`
- `src/semantic/dimension_resolver.py`
- `src/semantic/filter_resolver.py`
- `src/semantic/planner.py`
- `tests/test_semantic_layer.py`

Dependencies: Task 4.1.

#### Task 4.3: Extract constraint policy

Description: move `constraints.append(...)` logic into a policy layer tied to the rule registry.

Acceptance criteria:

- [ ] Constraint rules reference `rule_id`.
- [ ] Rules can be enabled/disabled by family in tests.
- [ ] Constraint policy does not parse arbitrary SQL; it only reads the semantic plan candidates.

Verification:

```powershell
uv run pytest tests/test_rule_registry.py tests/test_semantic_layer.py
```

Files likely touched:

- `src/semantic/constraint_policy.py`
- `src/semantic/rule_registry.yml`
- `src/semantic/planner.py`
- `tests/test_rule_registry.py`
- `tests/test_semantic_layer.py`

Dependencies: Task 4.2.

### Checkpoint 4 Verification

```powershell
uv run ruff check src/semantic tests
uv run pytest tests/test_semantic_layer.py tests/test_rule_registry.py
uv run pytest tests/test_sql_execution_block.py -k "semantic_plan or deterministic"
```

Decision gate:

- No broad behavior regression allowed.
- If refactor diff becomes too large, split into adapter-only commits before changing behavior.

## Checkpoint 5: Validator Simplification

Goal: make validation less brittle by blocking only high-confidence invariants.

### Tasks

#### Task 5.1: Split validator outputs into block/warn/pass

Description: replace boolean-only semantic validation decisions with severity and confidence.

Acceptance criteria:

- [ ] Validator result has `status in {pass, warn, block}`.
- [ ] Low-confidence plan-derived checks warn instead of blocking.
- [ ] DB syntax/schema failures still block.

Verification:

```powershell
uv run pytest tests/test_semantic_validators.py
```

Files likely touched:

- `src/semantic/validators.py`
- `src/semantic/validation_result.py`
- `src/agent/validation.py`
- `tests/test_semantic_validators.py`

Dependencies: Checkpoint 4.

#### Task 5.2: Retire or absorb legacy `check_semantic_rules`

Description: migrate surviving legacy checks into typed validator rules; remove direct "FIX EXACTLY" prompt behavior.

Acceptance criteria:

- [ ] No blocking rule returns hard-coded SQL as the fix.
- [ ] Legacy checks are either removed, converted to invariant validators, or documented as intentionally retained.
- [ ] Existing tests are rewritten against rule IDs and validator status.

Verification:

```powershell
uv run pytest tests/test_agent_improvements.py tests/test_semantic_validators.py
rg -n "FIX EXACTLY|check_semantic_rules" src tests
```

Files likely touched:

- `src/agent/validation.py`
- `src/semantic/validators.py`
- `tests/test_agent_improvements.py`
- `tests/test_semantic_validators.py`

Dependencies: Task 5.1.

### Checkpoint 5 Verification

```powershell
uv run pytest tests/test_semantic_validators.py tests/test_agent_improvements.py
uv run python -m evaluation.runners.run_ablation --variants V0 V10 --max-queries 20 --workers 2
```

Decision gate:

- False-positive workflow failures should decrease.
- EX must not drop on easy/medium smoke sets.

## Checkpoint 6: SQL Strategy Router And Compiler Registry

Goal: make SQL generation explicit: certified compiler first when appropriate, LLM fallback otherwise.

### Tasks

#### Task 6.1: Introduce `SQLStrategyRouter`

Description: extract strategy selection out of `generate_sql_node`.

Acceptance criteria:

- [ ] Router chooses among `certified_compiler`, `llm_generator`, and `llamaindex_draft` if enabled.
- [ ] Router records selected strategy and reason in metadata.
- [ ] Current behavior can be reproduced behind compatibility flags.

Verification:

```powershell
uv run pytest tests/test_sql_strategy_router.py
```

Files likely touched:

- `src/agent/sql_strategy.py`
- `src/agent/sql_generation.py`
- `tests/test_sql_strategy_router.py`

Dependencies: Checkpoint 5.

#### Task 6.2: Move deterministic SQL macros into compiler registry

Description: extract deterministic chart, analytic, scalar, grouped, and CID catalog macros into registered compilers.

Acceptance criteria:

- [ ] Each compiler declares `family`, `supports(plan)`, `confidence`, and `compile(plan)`.
- [ ] Unsupported plans return no SQL instead of partial guesses.
- [ ] Tests cover compiler selection and negative cases.

Verification:

```powershell
uv run pytest tests/test_sql_execution_block.py
uv run pytest tests/test_sql_strategy_router.py
```

Files likely touched:

- `src/agent/sql_compilers/`
- `src/agent/sql_generation.py`
- `src/agent/cid_catalog_sql.py`
- `src/agent/analytic_sql.py`
- `tests/test_sql_execution_block.py`
- `tests/test_sql_strategy_router.py`

Dependencies: Task 6.1.

### Checkpoint 6 Verification

```powershell
uv run ruff check src/agent src/semantic tests
uv run pytest tests/test_sql_execution_block.py tests/test_sql_strategy_router.py
uv run pytest tests/test_semantic_layer.py -q
```

Decision gate:

- Metadata must show why deterministic SQL was used.
- Unknown or low-confidence plans must fall back to LLM generation.

## Checkpoint 7: Targeted Repair Branch

Goal: keep repair, but make it narrow, auditable, and cheap.

### Tasks

#### Task 7.1: Add error classifier

Description: classify validator and execution errors into repairable and non-repairable categories.

Acceptance criteria:

- [ ] Categories include `sql_syntax`, `schema_reference`, `alias_scope`, `duckdb_quoting`, `timeout`, `high_confidence_contract`, `low_confidence_semantic`, `ambiguous_plan`, `unknown`.
- [ ] Only repairable categories trigger SQL repair.
- [ ] Ambiguous plan errors trigger replan or response, not SQL repair.

Verification:

```powershell
uv run pytest tests/test_sql_repair.py
```

Files likely touched:

- `src/agent/error_classifier.py`
- `src/agent/semantic_repair.py`
- `tests/test_sql_repair.py`

Dependencies: Checkpoint 6.

#### Task 7.2: Limit repair to one targeted attempt by default

Description: enforce small retry budget and specific repair prompt.

Acceptance criteria:

- [ ] Default `max_repair_attempts` is 1 for production.
- [ ] Repair prompt includes SQL, error category, `SemanticPlan`, relevant schema, and one targeted instruction.
- [ ] Repair does not regenerate the whole plan unless explicitly routed to replan.

Verification:

```powershell
uv run pytest tests/test_sql_repair.py tests/test_routing.py
```

Files likely touched:

- `src/agent/semantic_repair.py`
- `src/agent/execution.py`
- `src/agent/routing.py`
- `src/application/config/simple_config.py`
- `tests/test_sql_repair.py`
- `tests/test_routing.py`

Dependencies: Task 7.1.

### Checkpoint 7 Verification

```powershell
uv run pytest tests/test_sql_repair.py tests/test_routing.py tests/test_semantic_validators.py
uv run python -m evaluation.runners.run_ablation --variants V0 V4 V10 --max-queries 20 --workers 2
```

Decision gate:

- Repair should improve workflow success on repairable errors.
- Repair should not make correct SQL worse through semantic over-correction.

## Checkpoint 8: Prompt Simplification

Goal: reduce prompt rules to compact general principles plus structured plan context.

### Tasks

#### Task 8.1: Replace RULES A-O with rule-card rendering

Description: render only relevant rule cards selected from the rule registry and SemanticPlan.

Acceptance criteria:

- [ ] SQL prompt no longer injects the full A-O block by default.
- [ ] Prompt includes only relevant invariant summaries and selected domain context.
- [ ] Ablation flag can still reproduce old RULES A-O behavior for comparison.

Verification:

```powershell
uv run pytest tests/test_prompt_builder.py tests/test_semantic_layer.py
```

Files likely touched:

- `src/agent/prompt_builder.py`
- `src/semantic/rule_registry.py`
- `tests/test_prompt_builder.py`

Dependencies: Checkpoint 7.

#### Task 8.2: Remove duplicate schema warnings

Description: consolidate repeated table-specific warnings across prompt builder, schema node, and table templates.

Acceptance criteria:

- [ ] A table-specific warning has one owner.
- [ ] Prompt size decreases on representative queries.
- [ ] Required schema caveats remain visible for UTI, CID, procedures, geography, and socioeconomics.

Verification:

```powershell
uv run pytest tests/test_prompt_builder.py tests/test_routing.py
```

Files likely touched:

- `src/agent/prompt_builder.py`
- `src/agent/schema_node.py`
- `src/application/config/table_templates.py`
- `tests/test_prompt_builder.py`

Dependencies: Task 8.1.

### Checkpoint 8 Verification

```powershell
uv run pytest tests/test_prompt_builder.py tests/test_semantic_layer.py tests/test_sql_execution_block.py
uv run python -m evaluation.runners.run_ablation --variants V0 V7 V8 --max-queries 20 --workers 2
```

Decision gate:

- Token count should decrease.
- EX should not drop materially on targeted smoke.

## Checkpoint 9: Workflow Default Simplification

Goal: make the default graph reflect the simplified production path while preserving ablation controls.

### Tasks

#### Task 9.1: Introduce production profile

Description: define `production_simplified` config profile.

Acceptance criteria:

- [ ] CoT is disabled by default in simplified profile.
- [ ] Validator blocks only invariants by default.
- [ ] Repair is conditional and targeted.
- [ ] Existing full pipeline remains callable for ablation.

Verification:

```powershell
uv run pytest tests/test_routing.py tests/test_workflow_config.py
```

Files likely touched:

- `src/application/config/simple_config.py`
- `src/agent/workflow.py`
- `tests/test_workflow_config.py`
- `tests/test_routing.py`

Dependencies: Checkpoint 8.

#### Task 9.2: Add metadata contract for every node

Description: ensure every component records cost/latency/source decisions consistently.

Acceptance criteria:

- [ ] Metadata includes strategy, rule IDs, validator warnings/blocks, repair category, and timings.
- [ ] Ablation detail CSV includes these fields.
- [ ] Missing metadata fails focused tests.

Verification:

```powershell
uv run pytest tests/test_mlflow_tracker.py tests/test_evaluation_result_matching.py
```

Files likely touched:

- `src/agent/state_helpers.py`
- `src/agent/mlflow_tracker.py`
- `evaluation/runners/run_ablation.py`
- `tests/test_mlflow_tracker.py`
- `tests/test_evaluation_result_matching.py`

Dependencies: Task 9.1.

### Checkpoint 9 Verification

```powershell
uv run pytest tests/test_workflow_config.py tests/test_routing.py tests/test_mlflow_tracker.py
uv run python -m evaluation.runners.run_ablation --variants V0 V2 V4 V10 --max-queries 20 --workers 2
```

Decision gate:

- Simplified profile must be cheaper/faster than full pipeline in smoke.
- Full pipeline remains available for comparison.

## Checkpoint 10: Evaluation Dataset Split

Goal: separate regression stress testing from generalization measurement.

### Tasks

#### Task 10.1: Create dataset manifests

Description: define explicit manifests for dev regression, frozen holdout, and production-like sampled evaluation.

Acceptance criteria:

- [ ] `dev_regression` can include failure-enriched examples.
- [ ] `frozen_holdout` is not modified during implementation.
- [ ] `production_sample` records sampling method and date.
- [ ] Runners accept `--dataset` consistently.

Verification:

```powershell
uv run pytest tests/test_generalization_question_loader.py tests/test_dag_evaluation_ground_truth_arg.py
```

Files likely touched:

- `evaluation/datasets/`
- `evaluation/runners/run_ablation.py`
- `evaluation/runners/run_regression.py`
- `tests/test_generalization_question_loader.py`
- `tests/test_dag_evaluation_ground_truth_arg.py`

Dependencies: Checkpoint 9.

#### Task 10.2: Add family-level reporting

Description: ensure evaluation outputs can be grouped by anti-overfit family, semantic family, difficulty, and component variant.

Acceptance criteria:

- [ ] Reports show EX/cost/latency by family.
- [ ] Reports flag families where simplified profile regresses.
- [ ] Reports include confidence intervals or bootstrap intervals for decision runs.

Verification:

```powershell
uv run pytest tests/test_ablation_decision_report.py tests/test_generalization_rubric.py
```

Files likely touched:

- `evaluation/ablation/decision_report.py`
- `evaluation/agent/generalization_rubric.py`
- `tests/test_ablation_decision_report.py`
- `tests/test_generalization_rubric.py`

Dependencies: Task 10.1.

### Checkpoint 10 Verification

```powershell
uv run pytest tests/test_ablation_decision_report.py tests/test_generalization_question_loader.py
uv run python -m evaluation.runners.run_ablation --variants V0 V2 V4 V7 V10 LI2 --max-queries 30 --workers 2
```

Decision gate:

- No component removal is considered final until it passes holdout/family review.

## Checkpoint 11: Full Decision Run

Goal: decide which components become default after the refactor.

### Tasks

#### Task 11.1: Run full ablation comparison

Acceptance criteria:

- [ ] Run includes full pipeline, simplified profile, no CoT, no repair, no rules, no semantic validation, and LI2.
- [ ] Results include EX, workflow success, semantic validity, latency, cost, tokens, and family breakdown.
- [ ] Decision report explicitly marks keep/remove/demote for each component.

Verification:

```powershell
uv run python -m evaluation.runners.run_ablation `
  --variants V0 V2 V4 V7 V10 LI2 `
  --workers 2
```

Files likely touched:

- Generated artifact output only.
- `docs/generated/simplified_flow_decision_report_<run_id>.md`

Dependencies: Checkpoint 10.

#### Task 11.2: Run focused generalization sample

Acceptance criteria:

- [ ] At least 30 generalization questions run.
- [ ] CID/concept, top-N, rate denominator, UTI, geography, and unsupported-schema families are represented.
- [ ] Any regression receives a failure-family label before code changes continue.

Verification:

```powershell
uv run python -m evaluation.agent.run_generalization_exhaustion --limit 30
```

Files likely touched:

- Generated artifact output only.
- `docs/generated/simplified_flow_generalization_report_<run_id>.md`

Dependencies: Task 11.1.

### Checkpoint 11 Verification

```powershell
uv run pytest tests
uv run ruff check src evaluation tests
```

Decision gate:

- Simplified profile must have equal or better EX than V0 on decision evidence, or a clearly better cost/latency tradeoff with accepted risk.

## Checkpoint 12: Documentation And Release Readiness

Goal: leave the repo understandable for future work.

### Tasks

#### Task 12.1: Write architecture ADR

Acceptance criteria:

- [ ] ADR explains why the simplified flow became default.
- [ ] ADR documents what was demoted and why.
- [ ] ADR documents repair policy and validation severity policy.

Verification:

```powershell
git diff -- docs/adrs
```

Files likely touched:

- `docs/adrs/ADR-008-simplified-agent-flow.md`

Dependencies: Checkpoint 11.

#### Task 12.2: Update README evaluation guidance

Acceptance criteria:

- [ ] README explains default profile and full-pipeline ablation profile.
- [ ] README includes worker example for ablation.
- [ ] README warns that failure-enriched regression is not production accuracy.

Verification:

```powershell
git diff -- README.md
```

Files likely touched:

- `README.md`

Dependencies: Task 12.1.

### Checkpoint 12 Verification

```powershell
uv run pytest tests
uv run ruff check src evaluation tests
git status --short
```

Release gate:

- All tests pass or known failures are documented.
- Decision report exists.
- ADR exists.
- README is updated.
- Generated artifacts are ignored or intentionally promoted.

## Risk Register

| Risk | Impact | Mitigation |
|---|---:|---|
| Removing rules hides true domain knowledge | High | Convert rules into typed registry before deleting; ablate by family. |
| Simplified profile improves current regression but hurts production | High | Use holdout and generalization sample before default switch. |
| Planner split creates large risky diff | High | Preserve `build_semantic_plan()` API and split adapter-only commits. |
| Validator demotion allows wrong SQL through | Medium | Keep DB/schema/denominator/top-N-per-group invariants blocking. |
| Repair remains too broad | Medium | Classify errors and allow one targeted repair attempt by default. |
| Dataset artifacts pollute git status | Medium | Add artifact policy and keep only canonical reports tracked. |
| Cost of full decision run is non-trivial | Medium | Use smoke tiers before full run; only run full decision once checkpoints pass. |

## Implementation Order Summary

1. Baseline and rule inventory.
2. Decision/reporting harness.
3. CID concept generalization fix.
4. Planner split.
5. Validator severity split.
6. SQL strategy router and compiler registry.
7. Targeted repair branch.
8. Prompt simplification.
9. Workflow simplified profile.
10. Dataset split and family reporting.
11. Full decision run.
12. ADR/README/release readiness.

## Open Questions

- Should `LI2` become a first-class default strategy candidate if it keeps EX while reducing cost?
- What minimum EX delta is acceptable to trade for a large cost/latency reduction?
- Should generated historical evaluation results be removed from git in this branch or handled in a separate repository-hygiene branch?
- Which dataset should be frozen as the first holdout before implementation starts?

## Working Rules For This Branch

- Do not add new anonymous rules.
- Do not add tests that mention specific GT IDs unless the test is explicitly about evaluation plumbing.
- Every behavior change must include a family-level test or ablation note.
- Every checkpoint should leave the system runnable.
- Prefer small commits after each verified checkpoint.
