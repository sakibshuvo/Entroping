---
title: Surface Scope Policy
description: "Distinguish core, advanced, hidden, and deferred Entroping surfaces for honest launch claims."
type: reference
status: active
tags:
  - surface-scope
  - launch-boundary
  - studio
  - wiremock
  - graphql
  - soap
  - launch-readability
---

# Surface Scope Policy

This document classifies intentionally shipped feature surfaces for launch-readiness,
clarifying what is core, advanced, hidden, and deferred.

## Auditable Support Matrix

| Surface | Support level | Public boundary |
| --- | --- | --- |
| REST/OpenAPI | `shipped-core` | Public mainline: OpenAPI compilation, QAnstitution governance, Hurl execution, and CI reports. |
| GraphQL-over-HTTP | `internal-scaffold` | Hidden example and local SDL-to-Hurl scaffold; no public schema command or native GraphQL runtime guarantee. |
| SOAP/XML-over-HTTP | `internal-scaffold` | Hidden example and local WSDL-to-Hurl scaffold; no public schema command or SOAP runtime. |
| HTTP callback observation | `shipped-advanced` | Generic redacted traffic observation and reviewed freeze artifacts can preserve HTTP callback evidence. |
| AsyncAPI webhooks | `internal-scaffold` | Local contract scaffold only; no broker, message delivery, or webhook-specific runtime. |
| Proto HTTP transcoding | `internal-scaffold` | Local HTTP-transcoding scaffold only; native gRPC and streaming remain future work. |
| WebSockets | `future` | No handshake/message state-machine runtime is shipped. |
| Credentials | `shipped-bounded` | Environment-variable lookup is shipped; OS credential storage is future work. |
| QAnstitution imports | `shipped-bounded` | Local imports are shipped; HTTP(S) imports are rejected and remain future work. |
| `entroping studio` (read-only) | `shipped-advanced` | Optional local report/latest-run/redaction inspection; excluded from the primary pitch. |
| WireMock mappings (`freeze --mock`) | `shipped-advanced` | Supported optional component-test artifact; excluded from the primary pitch. |
| Dependency maps (`map --export`) | `shipped-advanced` | Supported optional visual evidence; not the primary value proposition. |

## Operational Rule

- **`shipped-core` surfaces** are what first-time users should read about in `README` and
  the public first-hour docs.
- **`shipped-advanced` surfaces** are shipped, documented, and tested, but
  described as optional. They may appear in demos or launch assets when they
  clarify value, but they should not displace the core README pitch.
- **`shipped-bounded` surfaces** expose only the behavior stated in the matrix;
  adjacent future behavior must not be inferred.
- **`internal-scaffold` surfaces** are kept for internal continuity and
  validation, but are not supported public workflows.
- **`future` surfaces** are not present-tense product promises and remain
  sequenced through GitHub Issues and ROADMAP.

## Implementation Pointers

- Surface decision references:
  - `docs/technical/COMMAND_CHEAT_SHEET.md` lists command visibility.
  - `docs/technical/CLI_COMPATIBILITY_AUDIT.md` records the compatibility contract.
  - `README.md` and `docs/index.md` keep the first-hour story focused.
  - `ROADMAP.md` keeps sequencing, not deep rationale.
