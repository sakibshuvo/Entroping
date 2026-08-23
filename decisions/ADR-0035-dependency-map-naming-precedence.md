---
title: ADR-0035 Dependency Map Naming Precedence
type: decision
status: accepted
date: 2026-08-21
tags:
  - eye
  - traffic
  - dependency-map
  - architecture
  - security
---

# ADR-0035: Dependency Map Naming Precedence

## Decision

Before rendering, map each normalized observed destination to a label from redacted traffic, policy `name`/`spec`, or P11 aggregates. Schema unchanged; no spec load/open/fetch/network resolution. Resolve before graph/approval write; no partial renderer artifact.

Strict precedence: one eligible HTTP(S) name/spec match > P11 inference (#1662) > normalized host; duplicates/ambiguity never use list order.

## Inputs and normalized identity

Observed input is `TrafficSessionCandidate.records[*].exchange.request.url`, method/path from redacted traffic. For an absolute HTTP(S) URL, parse without resolving; reject empty/malformed hostname, controls, userinfo, invalid port, malformed IP literals; ignore query/fragment. For DNS, use non-transitional UTS #46 with STD3 rules and IDNA2008 validity; reject invalid labels or mapping errors; canonicalize `faß.de` to `xn--fa-hia.de` (never `fass.de`), lowercase, and strip one trailing dot. For valid IPv4/IPv6, use `ipaddress.ip_address`, retaining compressed lowercase form and IPv6 brackets for display/authority identity. Port identity is scheme-independent: omit 80/443 for either scheme; retain every other valid port, so `http://svc:443` and `https://svc:443` collide. Keep the key internal; never expose it as a spec URL or query, credential, or request value.

Only an absolute HTTP(S) `spec` with valid hostname/literal can claim identity. Reuse host/port rules; reject userinfo, controls, query/fragment, malformed/ambiguous authority; ignore scheme (HTTP+HTTPS collide); never read paths. Relative/local specs cannot claim host; map never opens, fetches, DNS-resolves, or inspects them.

Name normalization: trim ASCII whitespace, NFC-normalize, Unicode casefold, then ASCII-map: whitespace/`.` separators become one `-`; collapse repeated `-`/`_`; allow only `a-z`, `0-9`, `_`, `-`, max 128 chars, no edge separator. Reject empty/control/secret-like values, URI/userinfo delimiters, quotes, brackets, graph syntax. Host fallback uses normalized identity, safe canonical port/DNS dots, renderer escaping.

## Matching and fallback contract (P06/P11/P12)

For each observed identity, collect dependency entries sharing normalized HTTP(S) spec identity before rendering:

| Dependency input | Result and behavior |
| --- | --- |
| Exactly one valid HTTP(S) identity and safe name | Eligible; normalized explicit name outranks P11 and host fallback. |
| No HTTP(S) identity, including local-path-only spec | Ineligible; do not inspect spec, use P11 then host. |
| Invalid, credential-bearing, unsafe, or ambiguous URL/name | Ineligible; do not echo value, use P11 then host. |
| Two or more valid entries for one normalized HTTP(S) host | Ambiguous; choose none, use P11 then host. |
| Same explicit name on different hosts | Label collision; keep hosts separate and suffix deterministically after precedence. |

Ineligible metadata may yield a deterministic map; malformed traffic, unsafe graph data, or renderer failure fails closed without partial artifact.

P11 consumes existing per-host `path_template`; only a shared first non-empty segment is a candidate. Exactly `{id}` is volatile; current compiler maps decimal, UUIDish, >=8-hex, redacted markers to `{id}`. If absent, volatile, mixed, control-bearing, or ambiguous, use normalized host; otherwise apply the same NFC/casefold/ASCII normalization. Never inspect queries, headers, bodies, vendors, or specs.

## Collisions, ordering, and renderers

Resolution is capture-order independent: aggregate normalized destination identity, uppercase method, redacted path template; sort before assigning labels/node IDs. For a shared base across hosts, sort normalized identities, keep the first base, then `-2`, `-3`, etc.; hosts never merge. Identical policy/traffic bytes yield identical labels, suffixes, route order, and renderer bytes.

The bridge graph model carries the label. Mermaid, Markdown, DOT, and PNG use it and stable order; renderers do not repeat precedence logic; escape dynamic fields. Markdown service/host columns, Mermaid/DOT labels, and PNG DOT source agree after format escaping. PNG approval metadata is value-free: no spec URLs, credentials, queries, raw traffic; summaries use resolved label/order. Resolve/render failure precedes output commit.

## Consequences and non-goals

Existing `dependencies[].name`/`spec` remain the QAnstitution contract; no schema/migration. Map generation read-only: no HTTP, DNS/registry lookup, provider call, or spec fetch. Raw spec URLs, local paths, credentials, queries, and bodies never become labels, diagnostics, approval metadata, or renderer input. Inference is a bounded display heuristic, not vendor/ownership discovery; host fallback states uncertainty. #1657 is P06 architecture; #1662 P11 fallback; #1663 P12 consumes the explicit-match bridge/core/renderer contract.

## References

- [ADR-0008: Freeze and map boundaries](ADR-0008-freeze-map-boundaries.md)
- [Technical Design Specification](../docs/technical/TDS.md#12-dependency-map-design)
- [QAnstitution dependency reference](../docs/technical/QANSTITUTION_REFERENCE.md#6-dependencies)
- [Issue #1657](https://github.com/sakibshuvo/Entroping/issues/1657)
- [Issue #1662](https://github.com/sakibshuvo/Entroping/issues/1662)
- [Issue #1663](https://github.com/sakibshuvo/Entroping/issues/1663)
