---
title: ADR-0033 Generated-Test Materialization Boundary
type: decision
status: accepted
date: 2026-08-14
tags: [generated-tests, mutation, boundary]
---

# ADR-0033: Generated-Test Materialization Boundary

## Decision

`report mutation-materialize` is a review-only materialization boundary that accepts
exactly one validated v1 mutation request and writes exactly one generated test file.
Core implementation is a private core API; Issue #1668 may expose it only through the
explicit experimental command `entroping report mutation-materialize` in the existing
`Experimental Design-Partner Evidence` panel and growth-policy registry.
It is intentionally non-launch-critical, non-stable-public, and is not part of ADR-0002 or
locked v4.1 compatibility obligations; it cannot be promoted to PRODUCT_SPEC locked surface
without a separate compatibility decision.
This ADR is the compatibility decision for that exact command name/flags in that panel.
Once added, its name/flags must satisfy existing compatibility and growth-policy contracts.
Issue #1668 must wire the command through `_experimental_qa.py` and `_deps.py`, update
`docs/meta/experimental-report-growth-policy.json`, and update strict order/count guards in
`tests/test_cli_report_experimental.py` for this command exposure. It may not be promoted to
stable locked compatibility without a separate decision.

Required root manifest keys are exact: `schema_version`, `category`,
`project_relative_source_path`, `expected_sha256`, `source_size_bytes`,
`source_mtime_ns`, `reviewed_seed`, `category_selector`, `review_decision_id`,
`evidence_ids`, and `candidate_id`.
Unknown/missing/unsafe/secret-like keys are rejected.

`schema_version` must be exactly `entroping.mutation-materialization.v1`.
`category` is exactly `status-code` or `request-shape`.
All request strings/keys/values are NFC-normalized UTF-8 and checked; controls and secret-like
tokens are rejected, including `project_relative_source_path`.
Non-NFC values are rejected.

`project_relative_source_path` is normalized UTF-8, project-relative, non-empty,
no empty component, no `.` or `..`, no absolute paths, no symlink segments, and no
unsafe control or secret-like characters. It must resolve to a regular file within size policy.

`expected_sha256` is exactly 64 lower-case hex.
`source_size_bytes` is integer `1..HURL_SOURCE_MAX_BYTES`.
`source_mtime_ns` is non-negative integer.
`reviewed_seed` is unsigned 32-bit integer `0..4294967295`.
`review_decision_id` and each `evidence_ids` item must match
`[A-Za-z0-9_.:-]{1,128}`.
`evidence_ids` must contain 1..32 items, sorted, unique.

`candidate_id` is supplied for equality validation only.
`candidate_id` is valid only when equal to:
`mut-` + first 24 lower-hex chars of SHA-256 over canonical JSON UTF-8 bytes of one
object containing exactly these members: `category`, `project_relative_source_path`,
`expected_sha256`, `reviewed_seed`, `category_selector`.
Canonical serialization recursively sorts object keys lexicographically, preserves JSON array order,
uses separators `(',', ':')`, emits no insignificant whitespace, uses `ensure_ascii=false` so valid non-ASCII NFC
chars remain UTF-8 (no `\\u` escapes), and hashes the accepted NFC bytes.

`category_selector` is a closed object and must be category-specific:
- `status-code`: `assertion_ordinal` (integer 0..9999) and `replacement_status` (100..599),
  exactly one status token selected.
- `request-shape`: `request_ordinal` (integer 0..9999),
  `json_pointer` (UTF-8 RFC 6901 text, 1..1024 bytes, starts with `/`, no control or secret-like chars,
  no unknown escapes, only `~0`/`~1`),
  and `corpus_id` exactly `request-shape-v1`.

Manifest source handling and write order:
resolve/path-traversal -> size policy -> read/hash/size/mtime/`mtime_ns` validation ->
selector/schema validation -> parser+formatter Hurl validation -> pre-write restat/re-hash ->
create-only atomic write.
Tightened pre-create check requires: bounded source read, SHA-256/size/`mtime_ns` check from manifest,
then `restat` + reread bounded source bytes + SHA-256/size/`mtime_ns` recheck against manifest and first read.
Any mismatch leaves source and destination unchanged.
Fail-closed includes oversized source and all request-shape pointer violations (invalid, missing, >1024 bytes).

Output path is fixed to `tests/generated/mutations/<candidate_id>.hurl`.
Destination validation is by resolved held directory identity anchored at project root: every
output ancestor component must be an existing directory, and directory resolution is performed
without following symlinks. Keep a validated destination directory identity/handle and
publish via create-exclusive file creation relative to that validated handle.
Reject path swap, symlink destination ancestry, non-directory ancestry, and any out-of-root
resolution. If the platform cannot provide no-follow component traversal plus held-directory-relative
create-exclusive publication (or an equivalent primitive), materialization is unsupported and fails
before source read and before any file operation.
The fixed destination ancestors must already exist as real directories; the materializer never creates
destination directories.
Revalidate destination identity immediately before publication; any validation/match
failure leaves source and destination unchanged.
Duplicate existing output fails before write.

Source safety line handling:
source must contain exactly one valid existing safety line and no pre-existing
reserved materializer keys: every canonical metadata key except `safety`
(`materializer_schema`, `review_only`, `candidate_id`, `mutation_category`, `mutation_seed`,
`source_sha256`, `source_size_bytes`, `source_mtime_ns`, `review_decision_id`, `evidence_ids`)
is forbidden in source.
The canonical materializer block is prepended once.
The original safety line is removed and replaced with the canonical `safety` value:
for `status-code`, emit the validated source safety; for `request-shape`, emit literal
`destructive`.

Exact metadata block key order and values:
`materializer_schema` = validated manifest `schema_version`
`review_only` = true
`candidate_id` = validated manifest `candidate_id`
`mutation_category` = validated manifest `category`
`mutation_seed` = base-10 validated `reviewed_seed`
`source_sha256` = validated manifest `expected_sha256`
`source_size_bytes` = validated manifest `source_size_bytes`
`source_mtime_ns` = validated manifest `source_mtime_ns`
`safety` = category-selected value defined above
`review_decision_id` = validated manifest `review_decision_id`
`evidence_ids` = comma-joined sorted validated `evidence_ids`
Each metadata line is exactly `# entroping: <key>=<value>` and lines are prepended once in this order.
No raw request/body values are embedded.
Missing, duplicated, invalid source safety fails closed.
Reserved materializer metadata keys in source fail closed.

Status-code flow: preserve every source byte except:
- removing exactly one source safety line,
- prepending the canonical metadata block,
- and mutating the selected `HTTP <status>` token with `replacement_status`.
`replacement_status` MUST differ from the selected source token; equal values fail as no-op.
Everything else in source remains unchanged.
`safety` canonical metadata equals the validated source safety value.

Request-shape flow: only one JSON scalar is eligible at `json_pointer`.
The selected scalar type is resolved with JSON type-strict semantics (for example boolean is
distinct from number).
Build candidates for that scalar type, then remove all type-equal corpus entries identical to the
selected source scalar value. If no candidates remain, fail closed before output.
Otherwise choose replacement with `reviewed_seed % len(remaining_candidates)`; replacement always
differs.
Select replacement by request type:
- string: `""`, `" "`, and 256 `x` characters.
- number: `-1`, `0`, `2147483647`.
- boolean: `false`, `true`.
- null: `""`, `0`, `false`.
Type filtering uses JSON type-strict equality for the current value; null current values do not match
non-null corpus entries, so all three null replacements above remain eligible.
No requirement is made that replacement preserve JSON type, only that the selected replacement index
is non-empty and eligible.
Canonical rendering must only replace the selected JSON body scalar in the selected request,
and preserve every other Hurl section unchanged apart from source safety removal and canonical metadata
insertion. For reviewed seeds, outputs may differ at the selected scalar only when the derived
corpus index changes.

Request-shape always sets `safety=destructive`; protected-run safety evaluation for generated artifacts
must refuse `safety=destructive` regardless of request method.
Issue #1669 must implement and test this downstream runtime contract.
No Hurl executable is invoked in this boundary.
Hurl validation is parser/formatter validation before atomic create-only write.

Fail-closed invariants include missing/invalid manifest or selectors, stale hash/size/mtime,
path escape, non-regular or symlink source, duplicated output, unsafe Hurl, missing review/evidence,
invalid candidate_id, unknown selector keys, oversize source, invalid/oversize pointer, missing/reviewed safety,
attempted overwrite/protected execution, request-shape target missing/multiple/non-JSON/object/array.

Beyond the explicit experimental adapter, no provider, network, authoritative-corpus,
test-execution, or overwrite authority is granted. Duplicate/overwrite attempts fail.

## Outcome

P17 and P18 can be implemented exactly from this contract.

## Non-goals

- broader runtime execution authority
- arbitrary provenance schema expansion
- mutation command implementation or runtime CLI behavior changes
