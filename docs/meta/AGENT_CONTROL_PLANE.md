---
title: Agent Control Plane
type: runbook
status: active
tags:
  - agents
  - codex
  - opencode
  - claude-code
  - gemini
  - notebooklm
  - qwen
---

# Agent Control Plane

This is the operating model for using multiple agents without turning the repo into prompt soup.

## Prime Directive

Codex owns factory design, Tier B/Tier C integration, and merge readiness for
sensitive lanes. OpenCode/DeepSeek may operate the Tier A autonomous lane
defined below only after the issue, worktree, PR, local gates, and CI prove
scope.

No helper agent is a source of truth. The hierarchy is:

1. Local repo files and tests.
2. GitHub issues, PRs, and CI.
3. ADRs and canonical product/technical docs.
4. Source exports under `<source-archive>`, usually `../entroping-specs` or `ENTROPING_SOURCE_ROOT`.
5. Agent summaries, chat context, NotebookLM answers, Gemini answers, Claude Code output, OpenCode output, and local Qwen output.

## Software Factory Operating Model

Codex owns factory design, Tier B/Tier C integration, and merge readiness for sensitive lanes.
Treat the parent Codex thread as the control room for security-sensitive,
runtime, architecture, release, and ambiguous work: it chooses the issue,
verifies local files, runs tests, updates required docs, opens the PR, waits
for CI, and merges only when the evidence is clean.

OpenCode and free-model workers receive bounded issue prompts. They can propose
tests, patches, review notes, alternate designs, documentation drafts, and
Tier A autonomous lane PRs. Their output is still untrusted until it is proven
against the repo, issue, deterministic gates, and GitHub CI.

Use `uv run python scripts/ai_jobs.py` when batching affordable worker tasks. It queues
bounded jobs under `.entroping/ai-jobs/`, maps cost profiles such as
`flash-free` to `opencode/deepseek-v4-flash-free` through the default
OpenCode engine and `pro` to `deepseek/deepseek-v4-pro`. For low-risk docs,
tests, guard-test, prompt-library, and non-runtime script proposals, submit
Tier A jobs with:

```bash
uv run python scripts/ai_jobs.py submit --autonomy-tier tier-a --mode review --file <path>
```

`--autonomy-tier tier-a` defaults OpenCode jobs to `flash-free`, records
provider lane, host, billing path, model id, context-manifest command, and
merge authority in the queued job, and injects a worker instruction that starts
from `scripts/context_pack.sh --mode implementation --manifest` before asking
for only the needed files/snippets. If Tier A is deliberately routed through
direct DeepSeek with `--engine deepseek-api`, the default profile is `flash`
instead of `pro`. Tier B and Tier C stay Codex/human reviewed and must not use
cheap routing to bypass security, architecture, provider, release, or runtime
authority.

The queue can still route paid jobs through direct DeepSeek with
`--engine deepseek-api` and `pro` mapped to `deepseek-v4-pro`. The queue runs
the oldest job through the selected bounded worker and lists completed artifact
directories for Codex review. The queue is an artifact conveyor, not an
authority layer: it never applies patches, commits, pushes, merges, or changes
release status.

Use the artifact-first worker contract for routine cheap/open-model work. Do
not run OpenCode interactively for routine cheap-worker work when a repo-owned
worker harness can capture bounded artifacts. Before dispatching queued cheap
workers, run `uv run python scripts/ai_jobs.py audit-routing --json` to surface stale Tier A
jobs that drifted into expensive routing. `run-next` performs both a queue-wide
preflight and a post-claim recheck of Tier A routing, source revision, selected
file digests, and any named GitHub issue; it restores the claimed job without
calling a worker when that evidence is stale or unavailable. Use
`uv run python scripts/ai_job_quarantine.py quarantine --json` to preview the
exact legacy records that would move, then repeat with `--apply` only after review. Original
bytes and a digest-bearing receipt remain under ignored repo-owned state. The
receipt is committed before the move so a retry can safely finish an interrupted
quarantine. Queue, quarantine, receipt, and requeue-record operations use
non-following directory handles and reject symlinked or non-regular state
entries. A current Tier A job whose named issue is no longer open and ready is
also a quarantine candidate rather than a repeated dispatch poison pill. A
quarantined job can return to the queue only through an explicit `requeue`
operation that rechecks the live issue, selected files, current revision, and
the requested cheap routing. A durable requeue record makes repeats idempotent
across queued, running, completed, and failed states. Neither command calls a
provider or substitutes a model automatically. After a worker finishes, use
`scripts/factory_review_packet.py --job-id <job-id> --json` or
`scripts/factory_review_packet.py --artifact-dir <artifact-dir> --json` to
build a compact review packet. Codex should review only the job metadata,
result summary, diff stat, git diff, changed files, and test output first. Do
not read raw stdout, stderr, provider responses, or full transcripts unless the
compact evidence is ambiguous. The Codex decision vocabulary is exactly:
`ACCEPT`, `REQUEST_SMALL_FIX`, `REWRITE_WITH_CODEX`, or `ESCALATE_SCOPE`.

## Model Provider Lane Taxonomy

[`provider-capability-registry.json`](provider-capability-registry.json) is the
only machine-readable authority for maintainer-factory lane ids, provider
hosts, billing paths, concrete model ids, capabilities, autonomy ceilings,
usage accounting, lifecycle, and queue defaults. Its generated authoring
schema is
[`provider-capability-registry.v1.schema.json`](provider-capability-registry.v1.schema.json).
The table below is an operator-oriented projection, not dispatch authority:

| Lane | Default use |
| --- | --- |
| `codex-spark` | Codex Spark review, proposal, comparison, or explicitly authorized implementation evidence. |
| `deepseek-api/direct` | Paid direct DeepSeek API through `scripts/deepseek_worker.py` or explicit `scripts/ai_jobs.py --engine deepseek-api` selection. It is the paid queue alternative for 24/7 review and patch proposals; the CLI's default engine remains OpenCode. |
| `opencode/native-deepseek` | DeepSeek configured directly inside the OpenCode host. Use only when explicitly requested or when the direct API lane is unsuitable. |
| `opencode-go/glm-5.2` | Candidate OpenCode Go subscription lane for GLM 5.2 experiments and comparison. |
| `opencode-go/kimi-k2.7-code` | OpenCode Go subscription lane for Kimi K2.7 Code coding experiments, long-context review, and model comparison. |
| `opencode-go/qwen3.7-max` | OpenCode Go subscription lane for Qwen3.7 Max coding experiments and model comparison. |
| `opencode-go/other` | Reserved OpenCode Go subscription lane for a curated paid model only after its exact model id is registered. |
| `local/offline` | Local model lane for private summarization, context compression, offline triage, and emergency fallback. |

The registry is repository-owned and non-secret. It does not contain
credentials, provider configuration, account state, price authority, or proof
that a candidate model is currently available. `active`, `candidate`,
`deprecated`, and `retired` preserve lifecycle without deleting historical
evidence. New queue dispatch requires an active lane and model. PR evidence may
refer to a registered historical or candidate model, but every paid lane must
match the exact registered lane, host, billing path, and model combination.
Unknown paid combinations fail closed; only a lane that explicitly allows
unlisted non-paid models may accept them.

Queue model `id` is the invocation identity for its engine. Metered entries
also expose provider-qualified `cost_model_id` values under `cost_provider_id`;
these are deterministic join metadata for the separate cost policy, never a
price or spending authorization. Route resolution enforces the lane's
`queue_dispatch` capability and autonomy ceiling before a queued job is
written. Legacy factory-metrics provider/model labels remain noncanonical until
issue #1573 binds them to job, diff, CI, merge, and regression evidence.

OpenCode Go is the Kimi/Qwen/model-variety lane, not the default DeepSeek lane.
Every worker artifact, metrics event, review note, or handoff should name the
provider host, billing path, and concrete model id when known. Do not write only
`OpenCode`, `DeepSeek`, or `Kimi` when the useful distinction is
`opencode-go/kimi-k2.7-code`, `opencode-go/qwen3.7-max`,
`opencode/native-deepseek`, or `deepseek-api/direct`.

Use `scripts/opencode_worker.py` instead of raw `opencode run` for repeatable
OpenCode/DeepSeek work. The worker has `review` mode for bounded findings and
`patch` mode for a patch proposal artifact under `.entroping/ai-reviews/`.
Patch mode never applies changes; Codex validates and applies any useful diff
inside the issue worktree, then runs the normal gates.

The worker requests OpenCode JSON events, consumes stdout incrementally under
the existing byte and timeout ceilings, and never persists raw JSONL. It writes
a minimal `usage-receipt.json` with schema
`entroping.opencode-usage-receipt.v1`: stable local/job/model correlation, a
hashed session identity, deduplicated step count, and validated input, output,
reasoning, cache, and cost totals only when accounting is complete. It reads to
EOF so usage emitted after final text is included. Missing, zero, malformed,
duplicated-conflicting, partial, timed-out, over-limit, or process-failed usage
is explicitly `unaccounted`; future paid automation must reject that state.
Raw reasoning, tool payloads, provider errors, event fragments, and child
stderr never enter the receipt, metadata, metrics, or queue record. Existing
sanitized final-text review and patch classification remains unchanged.

OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek lane. It may use
OpenCode-configured agents, plugins, MCP servers, hooks, shell/tools, and
GitHub integrations only when those capabilities are present in the active
OpenCode host and permissioned there. Codex-native plugins, skills, Codex Security, Browser, Computer Use, thread tools, and Codex-specific MCP state are
not automatically available unless the OpenCode host exposes equivalent
capabilities. The `scripts/opencode_worker.py` prompt includes an OpenCode Host Capability Context that preserves this boundary, forbids
`--dangerously-skip-permissions`, keeps selected-file snapshots as the worker's
truth surface, and keeps `entroping run` deterministic, Hurl-backed,
QAnstitution-governed, and provider-free.
Before an OpenCode Desktop or OpenCode CLI session edits files independently,
run `uv run python scripts/opencode_readiness.py --mode implementation
--require-clean --format json` from the issue worktree. For PR verification or
read-only monitoring, use `--mode verification` or `--mode monitoring` instead.
The preflight checks OpenCode availability, active repo path, branch/worktree
state, prompt-library guardrails, required workflow command surfaces, ignored
local OpenCode/Codex/artifact paths, and tracked local-state leaks without
reading provider keys, MCP credentials, local config values, prompts,
provider transcripts, raw traffic, or `.entroping/` artifacts. A failing
preflight is a stop condition; a passing preflight is only setup evidence, not
merge authority.
For non-maintainer checkout layouts, configure rejected stale checkouts and the
expected active parent with `--stale-repo-path`, `--expected-repo-prefix`,
`ENTROPING_STALE_REPO_PATHS`, or `ENTROPING_EXPECTED_REPO_PREFIX` rather than
rewriting the canonical prompt defaults.

Run `uv run python scripts/agent_toolchain.py --mode implementation --format json`
when a worker needs to know which local CLIs are available. The toolchain
preflight emits schema `entroping.agent-toolchain.v1`, performs PATH lookup
only, and does not execute scanners, read provider config, inspect local secret
stores, or make network calls. OpenCode readiness runs this preflight and
surfaces missing recommended tools as setup evidence; missing tools do not
grant permission to bypass tests, docs governance, security gates, or CI.

Agent CLI usage is classified by policy:

| Policy | Agent rule |
| --- | --- |
| `safe_default` | May be used during normal agent work for targeted local discovery, structured inspection, diff review, and measurement. Prefer these over broad context loads when they answer the issue question. |
| `guarded_local_only` | Use through a repo gate or an explicit focused command. Keep scope to the repo/worktree and do not scan home directories, provider config, raw traffic, `.entroping` artifacts, or local secret stores. |
| `manual_explicit` | Do not run automatically. Use only with explicit human/Codex approval, narrow scope, and a documented reason because the tool can execute workflow code, contact services, download databases, or traverse broad sensitive surfaces. |

Current manual-explicit tools are `act`, `trufflehog`, `semgrep`, `trivy`,
`syft`, and `grype`. Cheap workers may recommend one of these tools, but they
must not run it unless the issue packet or parent integrator authorizes the
exact command and scope.

Use `scripts/deepseek_worker.py` when OpenCode is the wrong dependency for a
paid DeepSeek Flash or Pro task. It calls DeepSeek's OpenAI-compatible chat
completion endpoint with an env-provided `DEEPSEEK_API_KEY`, includes selected
repo files as bounded UTF-8 prompt context, writes prompt, request,
stdout/stderr, response, proposal diff, and value-free metadata under
`.entroping/ai-reviews/`, and never applies patches. Before any artifact is
written or provider request is made, the worker rejects selected files that are
too large, binary, non-UTF-8, credential-path-like, or contain secret-like
content. Before generated output artifacts are written, the worker withholds
secret-like stdout/stderr and serialized response payloads, skips raw
response/proposal artifacts for that run, and records only value-free failure
evidence. This is maintainer-only local development tooling
for cheap worker output; it
does not replace Entroping's LiteLLM product boundary, and it must not be called
by `entroping run`.
Direct DeepSeek workers, including queued `uv run python scripts/ai_jobs.py run-next`
invocations, default to `--thinking disabled` to avoid empty hidden-reasoning
output and token burn for short reviews; opt into
`--thinking enabled --reasoning-effort high|max` only for deliberate deep-review
jobs. The generated prompt includes a Factory
Capability Context section defined in `scripts/deepseek_worker.py` that tells
direct DeepSeek API workers they have no live MCP, shell, filesystem, GitHub,
Codex skill, Spark, Kimi, or MCP execution unless that evidence is explicitly
supplied in the prompt. Retired generated context tooling is not part of the
active Entroping agent workflow and should not be requested from direct
DeepSeek workers. This context should reduce hallucinated tool use while
preserving Codex or human integration authority.

Queued OpenCode and DeepSeek children enforce byte caps. Subprocess stream
floods and timeouts terminate the process group and persist bounded failure
evidence; oversized DeepSeek HTTP responses are capped in-process and fail.
Factory retention is plan-first: inspect with
`python -m scripts.factory_retention plan` and delete only with locked,
fingerprint-checked `prune --apply`. Its scope is terminal jobs, reviews,
rotated logs, verified metrics archives, and terminal retention receipts under
`.entroping/`. Active logs are inventoried but protected; malformed,
legacy-unproven, unsettled, or externally uncertain evidence also stays
protected.

local Qwen/oMLX handles private summarization, triage, and low-risk review. Use
it for source-archive summarization, duplicate-finding, wording variants, and
offline review prompts before sending anything sensitive to cloud models.

Generated graph, wiki, and compression output is evidence, not authority. It
can help humans navigate relationships when useful, but local tests, source
files, ADRs, GitHub Issues, and CI decide truth.
Use the generated context-tool output paths documented in
`docs/meta/CONTEXT_MANAGEMENT.md`; generated graph, wiki, comprehension, and
compression artifacts remain local unless promoted through normal review.

The portable software-factory protocol is split between
`docs/meta/AGENT_ROLE_REGISTRY.yaml` and `scripts/factory_metrics.py`. The
registry gives Product Manager, Architect, Dev Agent, QA Agent, Code Review
Agent, Security Agent, Monitoring Agent, and Integrator roles consistent
missions, authority limits, context modes, Tier A cheap-worker routing
defaults, and metrics tags across Codex, Claude Code, OpenCode, DeepSeek,
Gemini, Spark, and local models. The metrics script records local JSONL events
with schema `entroping.factory-metrics.v1` under `.entroping/factory-metrics/`;
it is maintainer/development workflow evidence, not product runtime evidence,
and it must not store raw prompts, provider transcripts, secrets, raw traffic,
or product runtime evidence.
It also exports a per-issue report with schema
`entroping.factory-metrics-report.v1` so maintainers can compare context size,
estimated tokens, duration, cost, roles, provider/model usage, outcomes, and
accepted/rejected yield before future extraction into a reusable software
factory template. The report also includes an additive `model_comparison` view
grouped by issue, role, provider lane, and model id so OpenCode native
DeepSeek, direct DeepSeek API, OpenCode Go Kimi/Qwen, local models, Spark, and
Codex runs can be compared without collapsing missing cost or token evidence
into guessed values.
The same script owns the context-tool scorecard protocol with schema
`entroping.context-tool-scorecard.v1` and report schema
`entroping.context-tool-scorecard-report.v1`; use
`scripts/factory_metrics.py context-scorecard validate` and
`scripts/factory_metrics.py context-scorecard report --format json` before
promoting Obsidian/curated Markdown, Understand Anything, or any future
context tool into the active agent workflow. Retired generated context tooling
has been removed from the active workflow surface.
Recording from scripts is opt-in: use
`scripts/context_pack.sh --mode implementation --record-factory-metrics` to
measure context packs, use `uv run python scripts/ai_jobs.py run-next
--record-factory-metrics` for queued worker runs, and add
`--record-factory-metrics` plus, when needed, `--factory-metrics-ledger` to
direct `scripts/opencode_worker.py` or `scripts/deepseek_worker.py` worker
runs. These hooks record counts, status, duration, provider/model metadata,
and sanitized usage totals only. Accounted OpenCode runs use validated event
token totals and cost; unaccounted runs keep cost absent instead of guessing.
These metrics are not release proof, patch approval, or
a substitute for tests and CI.
Use `scripts/factory_metrics.py report --format json` for machine-readable
analysis and `scripts/factory_metrics.py report --format md --output
.entroping/factory-metrics/factory-report.md` for a local human review report.
Use `scripts/factory_metrics.py readiness --issue <issue> --format json` before
claiming an issue has software-factory readiness across quality, security,
context preservation, and token/cost efficiency. The readiness report uses
schema `entroping.factory-readiness.v1`, returns nonzero when a gate lacks
evidence, and prints only value-free event metadata and matched markers.
The factory framework owns workflow, context, metrics, and guardrails; the
project owns product truth.

### Portable role and metrics boundary

The portable role and metrics boundary is intentionally small. It describes
who may work, what evidence they owe, and which local metrics are safe to
compare before a future seed repo copies the factory workflow.

Portable role fields are role id, display name, mission, suggested context
modes, default autonomy tier, allowed authority, forbidden decisions, and
metrics tags. These fields are reusable because they describe work selection,
review accountability, stop conditions, and evidence routing. Entroping-only
role fields are product slogans, QAnstitution/Hurl ownership, Traffic is Truth
claims, release-readiness claims, package-index state, and any runtime or
security policy that only makes sense for this repository.

Portable metrics fields are issue number, role, provider lane, provider host,
model id, autonomy tier, context mode, context bytes or estimated tokens,
duration, sanitized token/cost totals when known, outcome, local gate names,
CI status, accepted/rejected decision, and known gaps. Entroping-only metrics
fields are source Hurl details, report payloads, raw traffic state, release
evidence contents, QAnstitution policy internals, package-index proof, and any
domain-specific readiness score that cannot be compared across repositories.
No one model, host, or billing path is mandatory; missing provider or cost
evidence stays explicit instead of being guessed.

Merge-trust evidence is the minimum packet another role needs before trusting
or merging work: GitHub issue scope, changed files, diff summary, tests or
docs gates run, PR-body evidence, provider lane and model id when a model was
used, autonomy tier, merge authority, CI rollup, and unresolved gaps. Tier A/B/C
authority limits still apply after the packet exists: Tier A may merge only
inside its declared low-risk lane after gates and green CI, Tier B requires
Codex or human review, and Tier C remains proposal-only.

Privacy and security boundary: factory roles and metrics must not store raw
provider transcripts, raw prompts, raw stdout/stderr captures, provider keys,
secrets, credentials, local env values, cookies, unredacted traffic, raw report
payloads, source Hurl contents, or unchecked generated artifacts. Generated
worker output remains evidence to inspect, not truth to trust.

One write agent per issue-scoped worktree. Parallelism comes from independent
issues, not from multiple agents editing the same files.

## Factory Template Extraction Inventory

This inventory is planning evidence for a future template scaffold, not the
template itself. Extract only workflow primitives that stay useful after
removing Entroping's product contract, then prove each extraction with its own
issue, tests, docs, and CI.

### Workflow primitives to evaluate for extraction

- Issue/worktree lifecycle: issue templates plus `scripts/start_issue.sh` and
  `scripts/finish_issue.sh` are candidates for extraction after proof because
  they encode the useful one-issue, one-branch, one-cleanup flow. A future
  template can keep that shape while replacing Entroping issue labels,
  project-board fields, and session-prompt product text.
- Gate ladder: `scripts/check.sh`, `scripts/feature_gate.sh`,
  `scripts/regression.sh`, and `scripts/audit_quality.sh` are candidates for a
  tiered verification ladder when each target repo supplies its own quality,
  security, architecture, docs, and dependency checks.
- Documentation governance and PR evidence: `scripts/doc_governance_check.sh`,
  `scripts/pr_body_check.py`, verification lanes, close keywords, and checked
  documentation-impact declarations are candidate review contracts.
- Agent control plane: Tier A/B/C lanes, provider-lane evidence, role registry
  routing, stop conditions, one write agent per issue worktree, and parent
  integrator ownership are candidate coordination rules.
- Context protocol: `scripts/context_pack.sh --manifest`, the decision
  registry, `.context/` handoffs, and targeted `rg`/source reads are candidate
  context-budget controls when each repo defines its own canonical evidence.
- Metrics: `scripts/factory_metrics.py readiness`, per-issue reports,
  context-pack byte/token estimates, model-comparison yield, and the rule that
  unknowns stay unknown are candidate measurement primitives.

### Portable context-as-evidence protocol

A reusable factory template should make context an auditable evidence trail,
not a second memory system. The source-of-truth priority is: local repo files
and tests; GitHub Issues, PRs, CI; decision registry and ADRs; product and
technical docs; external source/reference material; then chat memory last. A
worker may cite chat for intent, but merge readiness must point back to local
files, issue/PR evidence, CI, or reviewed external references.

Use manifest-only context when `scripts/context_pack.sh --manifest` identifies
the relevant files and the issue has a narrow named question. Use the full
context pack only when targeted reads, `rg`, the decision registry, and the
manifest cannot answer the question. Keep `.context/`, the decision registry,
prompt-library prompts, and handoff comments concise: record decisions,
commands, evidence paths, known gaps, and cleanup status instead of raw
transcripts or broad scratchpads.

Track whether the protocol is working with measurable signals: stale claim
rate, wrong-file references, human steering, context bytes/tokens, review
correction count, and accepted output ratio. Cleanup rules are part of the
protocol: generated local context stays ignored unless intentionally promoted,
ignored artifacts remain out of Git, and stale Markdown is pruned or archived
instead of copied into new strategy documents. Retired graph/compression tools
and Obsidian are optional aids, not default dependencies or authority layers
for a template.

### Minimal seed-repo contract

A future reusable seed repo needs only the smallest portable process surface:
agent instructions, issue lifecycle, gate ladder, context pack, decision
registry, role registry, and metrics. Those files and commands are reusable
only when they describe how work is selected, isolated, verified, reviewed,
and cleaned up; product behavior stays in the target repository.

Required CI evidence for a seed repo is: PR-body validation for close keywords,
documentation impact, autonomy and merge authority; docs governance; focused
tests for changed workflow docs or scripts; the repo's standard quality gate;
and a security/regression gate before autonomous merge. The local verification
expectations are the same shape: run the focused slice first, then the
declared lane, then wait for green CI before merge and finish cleanup.

Keep project-local rather than template-global decisions in the target repo:
product slogans, runtime boundaries, provider policy, dependency policy,
release claims, public docs, and security severity. Its explicit exclusions
are no Entroping runtime behavior, no QAnstitution branding reuse unless a
future project explicitly chooses it, no provider secrets, and no generated
vendor lock-in.

Tier A/B/C autonomy assumptions carry over only as review and stop-condition
language. Tier A requires low-risk scope, deterministic local gates, green CI,
and finish cleanup. Tier B requires Codex or human review. Tier C is
proposal-only for runtime, security, provider, release, dependency, secret, or
destructive filesystem surfaces. The required stop conditions are scope creep,
missing evidence, flaky or failing gates, forbidden provider use, context
drift, or any attempt to downgrade risk for budget reasons. Do not create an
external template repo from this issue.

### Portable anti-slop gate ladder

The portable anti-slop gate ladder starts with quick local checks and rises
through focused tests, docs governance, the standard quality gate, the
security/regression gate, and the quality audit. Each rung should be cheap
enough to run at its intended point and strict enough to stop weak model output
before it becomes review debt.

Required PR evidence is explicit: architecture impact, security impact, docs
governance status, test coverage, verification lane, commands run, autonomy
tier, merge authority, and known gaps. The rule is that model output is advisory until
deterministic gates and human/Codex review validate it against local files,
tests, CI, and issue scope.

The portable gates are the shape of the ladder: PR-body validation, focused tests,
docs governance, source formatting/lint/type checks, security/regression
checks, quality audit, CI rollup, and finish cleanup. The project-specific gates
are the target repo's architecture checks, product runtime boundaries,
dependency policy, release proof, coverage thresholds, and domain-specific
security rules.

Tier A minimum verification is focused tests for the touched surface,
documentation governance when docs change, the repo's standard gate or
security/regression gate when sensitive surfaces are touched, green CI, and
finish cleanup. Tier B/C work requires stricter gates plus Codex or human
review before merge. Stop on scope creep, flaky tests, missing evidence,
forbidden provider use, context drift, architecture uncertainty, or any request
to loosen existing Entroping CI, docs governance, security, or coverage
expectations.

### Entroping-specific product contracts

- QAnstitution governance, deterministic Hurl execution, Traffic is Truth, Hurl
  is the Enforcer, and Entroping branding are product truth, not template
  defaults.
- `entroping run` remains deterministic and LLM-free. A template must not copy
  provider-free runtime language unless the target product has the same
  deterministic boundary.
- The locked v4.1 CLI, product roadmap, reports, QAnstitution/Hurl evidence,
  source archive, Obsidian vault shape, and public launch claims stay in
  Entroping unless separately re-specified for another product.

### Blocked before generalizing

- Do not create a future template scaffold from this repo until extraction
  issues prove each primitive can run outside Entroping names, docs, GitHub
  labels, project-board fields, and product-specific tests.
- Do not generalize worker provider lanes until the target repo has its own
  secret handling, artifact hygiene, provider-evidence schema, and CI policy.
- Do not promote graph, wiki, compression, or generated context tools into a
  template without measured scorecard evidence and explicit ignored-output
  paths.
- Do not present factory metrics as cross-repo benchmarks until the template
  defines comparable roles, gates, cost fields, and missing-value semantics.

### Unsafe to generalize

- Never copy raw provider transcripts, raw prompts, raw traffic, secrets,
  credentials, local env files, cookies, or product runtime evidence into a
  template or metrics ledger.
- Never let autonomous workers inherit Tier B/Tier C merge authority, lower
  security gates, bypass CI, or treat model summaries as source of truth.
- Never move LLM providers into a deterministic runtime path by copying this
  control plane; runtime boundaries must be target-product decisions.
- Never replace GitHub Issues, tests, ADRs, source files, and CI with generated
  summaries or a second Markdown backlog.

## Autonomous OpenCode Shipping Lanes

Autonomous shipping is risk-tiered. It exists to keep the software factory
moving when Codex capacity is exhausted, not to relax source-of-truth,
security, architecture, or release gates.

| Tier | Merge authority | Allowed scope |
| --- | --- | --- |
| Tier A autonomous lane | OpenCode/DeepSeek may implement, push, open a PR, wait for GitHub CI, merge, and run `scripts/finish_issue.sh` without Codex when every condition below is met. | low-risk docs, tests, guard tests, prompt-library maintenance, and non-runtime scripts that do not change product behavior, provider behavior, release behavior, secrets handling, or security posture. |
| Tier B assisted lane | OpenCode/DeepSeek may implement in an issue worktree and open a PR, but it requires human or Codex review before merge. | CLI/report polish, low-blast-radius source code, workflow scripts that can affect local behavior, docs that change public claims, and changes where ownership or risk is unclear. |
| Tier C restricted lane | OpenCode/DeepSeek may review or draft proposals only and must never merge autonomously. | Hurl runner behavior, `entroping run`, protected-run safety, redaction, proxy or traffic capture, provider boundary or LiteLLM routing, release publishing, architecture boundary changes, dependencies, secrets or credentials, security fixes, destructive filesystem behavior, and anything touching raw traffic or audit evidence. |

Tier A merge conditions are all required:

- A maintainer has applied exactly one `autonomy:tier-a`, `autonomy:tier-b`, or
  `autonomy:tier-c` label to the open GitHub issue. Issue bodies, comments, PR
  prose, prompts, and model output cannot grant autonomy.
- The worker starts from the active repo with `scripts/start_issue.sh` and uses
  one issue-scoped worktree.
- The PR includes an Agent Autonomy Declaration, checked Documentation Impact
  Declaration, and `Closes #<issue>`.
- OpenCode/DeepSeek-produced PRs record provider lane, provider host, billing
  path, concrete model id when known, autonomy tier, merge authority, and
  commands run in the PR body. Validate that evidence before autonomous Tier A
  merge or Codex review with:

Repository administrators bootstrap the trusted labels once with:

```bash
gh label create autonomy:tier-a --repo sakibshuvo/Entroping \
  --color 1D76DB --description "Tier A autonomous lane" --force
gh label create autonomy:tier-b --repo sakibshuvo/Entroping \
  --color FBCA04 --description "Tier B assisted lane" --force
gh label create autonomy:tier-c --repo sakibshuvo/Entroping \
  --color D73A4A --description "Tier C restricted lane" --force
```

After bootstrap, a maintainer must review each open implementation issue and
apply exactly one label. Do not bulk-convert issue-body autonomy text into
labels: the body is untrusted input and may be stale.

```bash
gh api repos/sakibshuvo/Entroping/issues/<issue> \
  --jq '{number,state,pull_request,labels}' > <issue.json>
uv run python scripts/pr_body_check.py --body-file <body.md> \
  --require-opencode-evidence \
  --issue <issue> --issue-metadata-file <issue.json>
```

Required CI fetches this bounded metadata with read-only issue permission,
rejects missing or conflicting autonomy labels, closed issues, and pull
requests masquerading as issues, and refuses autonomous Tier A authority for
protected, sensitive, or release/quality guardrail diffs.

`scripts/factory_control_plane_policy.py` is the canonical protected-surface
policy. Tier A submission, pre-dispatch revalidation, proposed-patch review,
and PR readiness all consume it. The gate checks normalized aliases, both
sides of renames, every file in a multi-file patch, existing symlink
components, and generated symlink patches. A denial reports only relative paths
and reason codes, then routes the work to Codex or human review.

Changing the policy or adding a control-plane surface requires all of:

1. classify the surface under budget, provider routing, scheduler, repository
   authority, or credential boundaries;
2. update the canonical policy and focused direct, alias, rename, symlink, and
   multi-file tests where applicable;
3. update `.github/CODEOWNERS` when ownership coverage changes;
4. run the `release-ci-architecture` lane; and
5. record a durable decision update when authority changes.

CODEOWNERS makes ownership visible but does not itself require an approving
review. Required-review enforcement is a separate branch-protection setting.

- The diff touches only Tier A surfaces and contains no generated local state,
  secrets, `.entroping/`, provider transcripts, or local env files.
- Focused tests run for the touched surface, `scripts/regression.sh --security`
  passes, and GitHub CI is green.
- If the issue recorded factory metrics, `scripts/factory_metrics.py readiness
  --issue <issue> --format json` passes or the PR explains the missing local
  metrics evidence without downgrading required gates.
- The worker reviews the final diff, merges only through the PR, then runs
  `scripts/finish_issue.sh` from a separate checkout.

If a Tier A worker discovers the issue touches Tier B or Tier C scope, it must
stop at a safe checkpoint, report the files and failing or uncertain evidence,
and wait for human or Codex review. Tier B and Tier C work must not be
reclassified downward just to save model budget.

## Context Engineering Factory Boundary

GitHub Issues, PRs, CI, source files, tests, ADRs, the decision registry, and
QAnstitution/Hurl evidence remain the source-of-truth layer. These surfaces
decide whether Entroping behavior, architecture, security posture, and release
claims are real.

The active context-cost baseline is repo-native: `rg`,
`scripts/context_pack.sh`, `docs/meta/DECISION_REGISTRY.yaml`, GitHub issues,
source files, focused tests, CI, and `scripts/factory_metrics.py report`.
Use `scripts/factory_metrics.py readiness --issue <issue> --format json` to
turn those local metrics into a four-gate issue scorecard before a handoff or
merge readiness claim.
Context is evidence, not memory. Start each issue with one named question: what
local evidence is needed to change, review, or merge this issue? Do not add
generated context because it is interesting, visual, popular, or already
installed. Load extra context only when it answers the named issue question and
records an evidence pointer. Use `scripts/context_pack.sh
--record-factory-metrics` and `scripts/factory_metrics.py report` when token or
cost claims matter. No token-saving claim is accepted without measured local
evidence from the current workflow lane.

Obsidian, the LLM wiki, and curated source exports are the memory layer. They
preserve product evolution, source history, rejected ideas, open questions, and
durable rationale so a fresh agent can rehydrate the project without treating
old chat context as current truth.

Retired generated context tooling is not part of active agent workflow. Do not
route normal Codex, OpenCode, DeepSeek, or Spark sessions through external
context tools unless a future issue re-promotes a replacement through measured
scorecard evidence. Use `rg`, `scripts/context_pack.sh`,
`docs/meta/DECISION_REGISTRY.yaml`, GitHub issues, source files, tests, and CI
first. Understand Anything remains optional for human comprehension and
onboarding; it does not promote requirements, override tests, replace ADRs, or
approve patches. Any future retrieval or compression tool must not hide exact
diffs, failing test output, security findings, audit evidence, or
secrets-sensitive material.

`entroping run` remains deterministic, Hurl-based, QAnstitution-governed, and
provider-free. No context, graph, compression, or helper-agent tool may move LLM
providers into the run path or weaken the Hurl execution boundary.

Codex remains the factory architect and Tier B/Tier C merge owner, while Tier A
autonomous workers can merge only under the documented shipping lanes.
Budget-friendly workers can review, summarize, draft, critique, and ship
allowed Tier A changes, but every claim is checked against local files, tests,
docs, issues, ADRs, and CI before it becomes project truth.

## Context Pack

Every agent session should start with a deterministic context pack instead of a vague chat summary.

```bash
scripts/context_pack.sh --mode implementation
scripts/context_pack.sh --mode review
scripts/context_pack.sh --mode source
scripts/context_pack.sh --mode growth
scripts/context_pack.sh --mode handoff
```

Use `implementation` for coding, `review` for critique, `source` for Gemini/NotebookLM reconciliation, `growth` for open-source positioning, and `handoff` when starting a fresh thread.

Do not route context packs through external generated-context tooling. The
active workflow is the curated pack plus targeted repo discovery with `rg`,
source reads, tests, docs, GitHub issues, ADRs, and CI evidence.

## Agent Roles

`docs/meta/AGENT_ROLE_REGISTRY.yaml` is the machine-readable role registry for
portable worker prompts, context-pack routing, and metrics tags. Keep the table
below as the human summary and the registry as the consumable contract. Role
definitions are a routing aid, not authority to override repo evidence,
GitHub Issues, ADRs, tests, CI, or QAnstitution/Hurl evidence.

| Agent | Best Use | Not Allowed To Decide Alone |
| --- | --- | --- |
| Codex | Factory design, Tier B/Tier C integration, security fixes, repo scripts, final validation | Product strategy without updating docs/issues |
| Claude Code | Independent implementation proposal, code review, refactor critique | Tier B/Tier C merge without human or Codex validation |
| OpenCode | Cheap review worker, test ideas, docs drafts, alternative analysis, Tier A autonomous implementation | Security severity, architecture authority, release readiness, Tier B/Tier C merge authority |
| Gemini | Broad product synthesis, marketing angles, source debate, launch copy | Current repo facts unless given a context pack |
| NotebookLM | Source-grounded Q&A over exports and spec history | Implementation truth after code changes |
| local Qwen via oMLX | Private/offline summarization, low-risk review, wording variants | Final code, security, release, or architecture decisions |

## Multi-Session Rules

- One write agent per issue, branch, and file family.
- Many read-only review agents are acceptable.
- Do not let two agents edit the same source area concurrently.
- Use `scripts/start_issue.sh` for issue worktrees when there is a GitHub issue.
- Use `scripts/context_pack.sh --mode review` when asking another model to review a diff.
- Parent Codex thread resolves Tier B/Tier C conflicts against local files,
  tests, docs, ADRs, and CI.
- Tier A autonomous workers stop and escalate if they touch Tier B/Tier C scope
  or collide with another active worker.

## Marathon Pattern

Run marathons in waves:

1. Pick 2-4 independent GitHub issues.
2. Start one worktree per issue with `scripts/start_issue.sh`.
3. Keep one parent Codex thread as integrator for Tier B/Tier C or mixed-risk work.
4. Give helper agents read-only review prompts unless a worktree is isolated.
5. Require each write branch to pass `scripts/regression.sh`.
6. Require `scripts/regression.sh --security` for dependency, subprocess, proxy, path, LLM, report, or traffic-state changes.
7. Merge Tier A autonomously only when the lane conditions are met; otherwise merge only after human or Codex review.
8. Run `scripts/finish_issue.sh` after merge to clean worktrees and project-board state.

## Codex-Outage OpenCode/DeepSeek Work Queue

#702 is the one-week Codex-low-availability queue for OpenCode Desktop,
OpenCode Go, and paid DeepSeek API work. It is a queue index, not a separate
source of truth and not product roadmap proof. Child issues own implementation;
the queue keeps the worker order, risk tier, provider lane, and merge authority
explicit so low-cost workers do not improvise architecture, security, or release
decisions while Codex capacity is low.

Operating model:

- Codex produces guardrails, backlog packets, architecture boundaries, and
  review prompts while available.
- OpenCode/DeepSeek workers execute only one issue per worktree using
  `scripts/start_issue.sh`.
- Tier A issues may merge autonomously only after the documented lane
  conditions, local gates, GitHub CI, `Closes #<issue>`, and
  `scripts/finish_issue.sh` cleanup.
- Tier B issues may produce a PR, but Codex or a human must review before
  merge.
- Tier C issues are review/proposal only and must not merge autonomously.

Provider lanes:

The canonical set and exact model combinations come from
`docs/meta/provider-capability-registry.json`; these bullets are operational
examples and cannot authorize an unregistered paid route.

- `opencode/native-deepseek`: OpenCode host using paid DeepSeek inside
  OpenCode.
- `deepseek-api/direct`: direct paid DeepSeek API through repo-local worker
  scripts.
- `opencode-go/kimi-k2.7-code`: OpenCode Go Kimi lane after that subscription
  is active.
- `opencode-go/glm-5.2`: OpenCode Go GLM lane after that subscription and exact
  registered model are active.
- `opencode-go/qwen3.7-max`: OpenCode Go Qwen lane after that subscription is
  active.
- `opencode-go/other`: other OpenCode Go curated models.

Every worker handoff must name provider host, billing path, and concrete model
id when known. Use `opencode-desktop-handoff.md` for OpenCode Desktop or
OpenCode Go sessions. Use `issue-worker.md` only when the issue is already
scoped and the autonomy tier is clear.

Recommended rehearsal order:

This order records the planned queue and the evidence trail across completed
and remaining child issues. GitHub issue state remains authoritative for whether
each child is still open, merged, blocked, or finished.

1. #703 - first `opencode/native-deepseek` rehearsal for prompt-library docs
   and a guard test.
2. #704 - Codex-outage daily operations prompt.
3. #705 - OpenCode Desktop plugin/MCP/hook setup checklist.
4. #708 - OpenCode-only week monitoring prompt.
5. #709 - architecture-boundary brief template for worker issue packets.
6. #706 - PR body validator for provider-lane evidence.
7. #707 - factory metrics model-comparison report.
8. #710 - prove or discard optional context-tool value.

Queue acceptance rules:

- Child issues must be ready, narrow, and tagged with a clear autonomy tier.
- Each child issue must name allowed files, forbidden files, focused tests,
  gates, and merge authority.
- The queue must include at least one immediate `opencode/native-deepseek`
  rehearsal issue.
- OpenCode Go model-variety work for Kimi/Qwen starts only after the
  subscription is active and the handoff names the concrete lane.
- No issue in this queue may ask unattended workers to touch `entroping run`,
  Hurl runner behavior, redaction, proxy capture, provider runtime boundaries,
  release publishing, secrets, dependencies, raw traffic, or audit evidence.
- Do not lower security, docs governance, CI, or coverage expectations, and do
  not treat model output as source of truth.
- Compare Codex, DeepSeek, Kimi, Qwen, or local/offline performance through
  issue outcome, diff quality, tests, CI, and review findings, not anecdotes.
  Use `model-comparison-trial.md` for the trial prompt and
  `scripts/factory_metrics.py report` for local value-free metrics summaries.

## Hallucination Controls

- Every implementation claim needs a file path, test, command, issue, or ADR.
- Every source-history claim needs a source path from `sources/SOURCE_MAP.md`.
- Every product change must be promoted into a canonical doc or ADR before code follows it.
- Every bug fix should add or update a regression test when deterministic reproduction is possible.
- Every model-generated suggestion is untrusted until checked against local files.

## Prompt Template

Reusable copy-paste prompts live in
`docs/meta/prompt-library/README.md`. Keep durable agent policy in this control
plane and keep session launchers in the prompt library.

```text
Work in <repo-root>.
Use AGENTS.md as the project rules.
Use scripts/context_pack.sh --mode implementation as the context pack.
Implement only the named GitHub issue or task.
Preserve the locked v4.1 command surface.
Declare the autonomy tier before implementation.
Use TDD where behavior is testable.
Run scripts/regression.sh before commit.
Run scripts/regression.sh --security for security-sensitive or dependency work.
Update docs and .context only when behavior, workflow, or durable lessons changed.
Return file/line evidence, commands run, and known gaps.
```

## Codex-Specific Flow

Codex should be boring and evidence-driven:

1. Read `AGENTS.md`.
2. Run `scripts/context_pack.sh --mode implementation` or read its listed files.
3. Inspect code before editing.
4. Write failing tests first where practical.
5. Apply narrow changes.
6. Run focused tests, then `scripts/regression.sh`.
7. Run `scripts/regression.sh --security` for sensitive boundaries.
8. Review `git diff`.
9. Update `.context/` and docs only when useful.
10. Commit with a Conventional Commit message.

Do not commit `.codex/` project state. Project behavior belongs in `AGENTS.md`, scripts, tests, docs, issue prompts, and CI.
