"""Documentation guardrails for practical traffic-capture limits."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_GUIDE = REPO_ROOT / "docs" / "user" / "USER_GUIDE.md"


def test_user_guide_documents_real_watch_environment_limits() -> None:
    guide = USER_GUIDE.read_text(encoding="utf-8")
    normalized_guide = re.sub(r"\s+", " ", guide)

    assert "### Practical `watch` Limits" in guide

    required_phrases = (
        "Install the mitmproxy CA certificate for each client, browser, or runtime",
        "corporate VPNs or upstream proxies",
        "certificate pinning",
        "bypass system proxy settings",
        "authentication and session headers",
        "Do not capture traffic unless you have permission",
        "Start with a local demo, test fixture, or development environment",
        "redaction happens before persistence",
        "responsible for capture authorization and review",
    )
    for phrase in required_phrases:
        assert phrase in normalized_guide
