#!/usr/bin/env python3

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.provider_capability_schema import (  # noqa: E402
    provider_capability_json_schema,
)


def main() -> None:
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "meta"
        / "provider-capability-registry.v1.schema.json"
    )
    _ = schema_path.write_text(
        json.dumps(provider_capability_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
