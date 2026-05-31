#!/usr/bin/env python3
"""Regenerate the committed QAnstitution JSON Schema file."""

import json
from pathlib import Path

from entroping.models.qanstitution_schema import qanstitution_json_schema


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    schema_path = repo_root / "docs" / "technical" / "qanstitution.schema.json"
    schema = qanstitution_json_schema()
    schema_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
