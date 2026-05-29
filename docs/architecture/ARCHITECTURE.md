---
title: Architecture
type: architecture
status: active
tags:
  - architecture
  - mermaid
  - plantuml
---

# Architecture

Entroping uses Ports and Adapters. The domain layer defines data structures and pure translation rules. Primary adapters accept user commands. Secondary adapters talk to tools, files, databases, proxies, and models.

## Package Boundaries

```mermaid
flowchart TB
  subgraph Domain["Domain"]
    Models["src/entroping/models"]
    Bridge["src/entroping/bridge"]
  end

  subgraph PrimaryAdapters["Primary Adapters"]
    CLI["src/entroping/cli"]
    Studio["src/entroping/studio"]
  end

  subgraph SecondaryAdapters["Secondary Adapters"]
    Core["src/entroping/core"]
    Brain["src/entroping/brain"]
  end

  CLI --> Models
  CLI --> Bridge
  Studio --> Models
  Studio --> Bridge
  Core --> Models
  Core --> Bridge
  Brain --> Models
  Brain --> Bridge
  Bridge --> Models
```

Rules:

- `models` imports no adapters.
- `bridge` imports `models` and pure utilities only.
- `cli`, `core`, `brain`, and `studio` depend inward.
- Hurl execution is isolated behind `core`.
- LLM calls are isolated behind `brain`.

## Runtime Governance Flow

```mermaid
sequenceDiagram
  actor User
  participant CLI as Entroping CLI
  participant Policy as QAnstitution Loader
  participant Injector as Gate Injector
  participant Hurl as Hurl Binary
  participant Reports as Report Writer

  User->>CLI: entroping run --env ci --tag smoke --ci
  CLI->>Policy: load and validate effective law
  Policy-->>CLI: gates, settings, known failures
  CLI->>Injector: source tests plus matching gates
  Injector-->>CLI: temporary execution material
  CLI->>Hurl: subprocess execution
  Hurl-->>CLI: exit code, stdout, stderr
  CLI->>Reports: write junit/html/json/drift
  Reports-->>CLI: artifact paths
  CLI-->>User: deterministic summary and exit code
```

## PlantUML Component Source

```plantuml
@startuml
skinparam componentStyle rectangle

actor "Developer" as Dev
component "Entroping CLI" as CLI
component "Domain Models" as Models
component "Bridge Compilers" as Bridge
component "Hurl Runner" as HurlRunner
component "LiteLLM Router" as Brain
component "mitmproxy Addon" as Proxy
database "SQLite State" as DB
component "Report Writer" as Reports
component "Hurl Binary" as Hurl
component "API Under Test" as API

Dev --> CLI
CLI --> Models
CLI --> Bridge
Bridge --> Models
CLI --> HurlRunner
HurlRunner --> Hurl
Hurl --> API
CLI --> Brain
CLI --> Proxy
Proxy --> API
Proxy --> DB
CLI --> Reports
Reports --> Models
@enduml
```

More diagrams live in [[docs/architecture/DIAGRAMS|DIAGRAMS]].

