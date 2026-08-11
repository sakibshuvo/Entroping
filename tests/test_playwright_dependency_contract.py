"""Public manifest contract for the Playwright accessibility toolchain."""

import json
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]


def _json_object(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_playwright_tools_share_one_exact_core_type_identity() -> None:
    package = _json_object(REPO_ROOT / "package.json")
    lock = _json_object(REPO_ROOT / "package-lock.json")
    dev_dependencies = cast(dict[str, str], package["devDependencies"])

    playwright_version = dev_dependencies["@playwright/test"]
    assert dev_dependencies.get("playwright-core") == playwright_version

    packages = cast(dict[str, dict[str, Any]], lock["packages"])
    root_dev_dependencies = cast(dict[str, str], packages[""]["devDependencies"])
    assert root_dev_dependencies["playwright-core"] == playwright_version
    assert packages["node_modules/playwright"]["dependencies"]["playwright-core"] == (
        playwright_version
    )

    core_installations = {
        path: metadata["version"]
        for path, metadata in packages.items()
        if path == "node_modules/playwright-core"
        or path.endswith("/node_modules/playwright-core")
    }
    assert core_installations == {"node_modules/playwright-core": playwright_version}
