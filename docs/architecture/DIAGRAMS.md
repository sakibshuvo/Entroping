# Entroping Diagrams

**Contract version:** 4.1
**Product maturity:** Alpha

This file contains Mermaid and PlantUML diagrams that can be copied into compatible renderers.

## 1. Product System Context

```mermaid
flowchart LR
  Developer["Developer or QA"] --> CLI["Entroping CLI"]
  Architect["Architect"] --> QAN["qanstitution.yaml"]
  CLI --> Hurl["Hurl Binary"]
  CLI --> Eye["mitmproxy Eye"]
  CLI --> Brain["LiteLLM Brain"]
  Eye --> State[".entroping/state.db"]
  QAN --> CLI
  Hurl --> API["API or Microservices"]
  API --> Hurl
  CLI --> Reports["Reports"]
  Reports --> CI["CI/CD"]
```

## 2. Hexagonal Architecture

```mermaid
flowchart TB
  subgraph Domain["Domain"]
    Models["models: schemas"]
    Bridge["bridge: transforms and policy compiler"]
  end

  subgraph Primary["Primary Adapters"]
    CLI["cli: Typer commands"]
    Studio["studio: Textual TUI"]
  end

  subgraph Secondary["Secondary Adapters"]
    Core["core: Hurl, DB, reports, proxy"]
    Brain["brain: LiteLLM agents"]
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

## 3. Command Lifecycle

```mermaid
flowchart TD
  Init["entroping init"] --> Law["Define qanstitution.yaml"]
  Law --> Choice{"Source of truth?"}
  Choice -->|Spec or stories| Build["architect build"]
  Choice -->|Existing tests| Refactor["architect refactor"]
  Choice -->|Live behavior| Watch["watch"]
  Watch --> Freeze["freeze"]
  Build --> Run["run"]
  Refactor --> Run
  Freeze --> Run
  Run --> Reports["reports"]
  Reports --> Decision{"Blocking failures?"}
  Decision -->|Yes| Bug["report bug"]
  Decision -->|No| Ship["Merge or deploy"]
```

## 4. Architect Build Sequence

```mermaid
sequenceDiagram
  actor User
  participant CLI as Entroping CLI
  participant Config as QAnstitution Loader
  participant Brain as Builder/Auditor/Breaker
  participant Merge as Hurl Merge Engine
  participant Check as Syntax Validator

  User->>CLI: architect build --strategy merge --prompt
  CLI->>Config: load effective policy and agents
  Config-->>CLI: validated config
  CLI->>Brain: task, persona, sources, policy
  Brain-->>CLI: structured test plan and Hurl edits
  CLI->>Merge: apply scoped changes
  Merge-->>CLI: candidate files
  CLI->>Check: validate generated Hurl
  Check-->>CLI: syntax result
  CLI-->>User: diff summary and artifacts
```

## 5. Run and Gate Injection Sequence

```mermaid
sequenceDiagram
  actor User
  participant CLI as entroping run
  participant Policy as QAnstitution
  participant Injector as Gate Injector
  participant Hurl as Hurl Binary
  participant Reports as Report Writer

  User->>CLI: run --env ci --tag smoke --ci
  CLI->>Policy: load imports and validate
  Policy-->>CLI: effective gates
  CLI->>Injector: test files plus matching gates
  Injector-->>CLI: temporary execution files
  CLI->>Hurl: subprocess run
  Hurl-->>CLI: exit code, stdout, stderr
  CLI->>Reports: write junit/html/json
  Reports-->>CLI: artifact paths
  CLI-->>User: summary and exit code
```

## 6. Eye Observation Flow

```mermaid
flowchart LR
  Client["Browser, curl, Postman, Bruno, Insomnia"] --> Proxy["entroping watch / mitmproxy"]
  Proxy --> Target["Target API"]
  Target --> Proxy
  Proxy --> Redact["Redaction Pipeline"]
  Redact --> DB["SQLite traffic store"]
  DB --> Freeze["entroping freeze"]
  Freeze --> HurlTests["Generated Hurl tests"]
  Freeze --> Mocks["WireMock mappings"]
  DB --> Map["entroping map"]
  Map --> Graph["Dependency graph"]
```

## 7. Multi-Repo Governance

```mermaid
flowchart TB
  Central["central-quality repo"] --> Sec["security.yaml"]
  Central --> Perf["performance.yaml"]
  Sec --> A["service-a/qanstitution.yaml"]
  Perf --> A
  Sec --> B["service-b/qanstitution.yaml"]
  Perf --> B
  Sec --> C["service-c/qanstitution.yaml"]
  Perf --> C
  A --> CIA["service-a CI run"]
  B --> CIB["service-b CI run"]
  C --> CIC["service-c CI run"]
  A --> E2E["platform-quality E2E repo"]
  B --> E2E
  C --> E2E
```

## 8. Test Diamond

```mermaid
flowchart TB
  Unit["Unit tests: owned by codebase"] --> Contract["Contract and API tests: Entroping core"]
  Contract --> Integration["Integration and component tests: Entroping core"]
  Integration --> E2E["API-driven E2E: Entroping supported"]
  E2E --> UI["Visual UI tests: external tools"]
```

## 9. PlantUML Component Diagram

```plantuml
@startuml
skinparam componentStyle rectangle

actor "Developer" as Dev
component "Entroping CLI" as CLI
component "Studio TUI" as Studio
component "Domain Models" as Models
component "Bridge Compilers" as Bridge
component "Hurl Runner" as HurlRunner
component "Gate Injector" as GateInjector
component "mitmproxy Addon" as Proxy
database "SQLite State" as DB
component "LiteLLM Router" as Brain
component "Report Writer" as Reports
component "Hurl Binary" as Hurl
component "API Under Test" as API

Dev --> CLI
Dev --> Studio
CLI --> Models
CLI --> Bridge
Studio --> Models
HurlRunner --> GateInjector
GateInjector --> Bridge
HurlRunner --> Hurl
Hurl --> API
Proxy --> API
Proxy --> DB
Brain --> Models
Reports --> Models
CLI --> Reports
CLI --> HurlRunner
CLI --> Proxy
CLI --> Brain

@enduml
```

## 10. PlantUML Run Sequence

```plantuml
@startuml
actor User
participant "CLI" as CLI
participant "QAnstitution Loader" as Loader
participant "Gate Injector" as Injector
participant "Hurl Runner" as Runner
participant "Hurl Binary" as Hurl
participant "Report Writer" as Reports

User -> CLI: entroping run --env ci --tag smoke --ci
CLI -> Loader: load and validate imports
Loader --> CLI: effective policy
CLI -> Injector: match gates to tests
Injector --> CLI: execution files
CLI -> Runner: execute with timeout
Runner -> Hurl: subprocess
Hurl --> Runner: stdout, stderr, exit
Runner --> CLI: typed result
CLI -> Reports: write junit/html/json
Reports --> CLI: artifact paths
CLI --> User: summary and exit code
@enduml
```

## 11. PlantUML Legacy Rescue Activity

```plantuml
@startuml
start
:Start entroping watch;
:Route client through proxy;
:Exercise legacy workflow;
:Redact and store traffic;
if (Session useful?) then (yes)
  :Freeze session;
  :Generate Hurl tests;
  if (External dependency?) then (yes)
    :Generate WireMock mappings;
  endif
  :Run regression suite;
  if (Passes QAnstitution?) then (yes)
    :Commit reviewed tests;
  else (no)
    :Generate bug report;
  endif
else (no)
  :Record another session;
endif
stop
@enduml
```

## 12. PlantUML Deployment View

```plantuml
@startuml
node "Developer Machine" {
  artifact "entroping CLI" as DevCLI
  artifact "hurl binary" as DevHurl
  artifact "qanstitution.yaml" as DevPolicy
  artifact "tests/*.hurl" as DevTests
  database ".entroping/state.db" as DevState
}

node "CI Runner" {
  artifact "entroping CLI" as CiCLI
  artifact "hurl binary" as CiHurl
  artifact "JUnit report" as CiJUnit
}

node "Service Runtime" {
  component "API under test" as ApiUnderTest
  component "Dependent services" as DependentServices
}

DevCLI --> DevPolicy
DevCLI --> DevTests
DevCLI --> DevState
DevCLI --> DevHurl
DevHurl --> ApiUnderTest
CiCLI --> CiHurl
CiHurl --> ApiUnderTest
ApiUnderTest --> DependentServices
@enduml
```
