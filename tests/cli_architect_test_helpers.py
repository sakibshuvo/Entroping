from cli_test_support import (
    Path,
    json,
)


def _agent_run_manifest_payloads() -> list[dict[str, object]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((Path(".entroping") / "agent-runs").glob("*.json"))
    ]
