#!/usr/bin/env python3

import json
from pathlib import Path

from scripts.factory_cost_policy_schema import factory_cost_policy_json_schema


def main() -> None:
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "meta"
        / "factory-cost-policy.v1.schema.json"
    )
    _ = schema_path.write_text(
        json.dumps(factory_cost_policy_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
