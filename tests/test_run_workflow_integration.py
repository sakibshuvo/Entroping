"""Integration proof for CLI run workflow wiring."""

import json
from pathlib import Path
from textwrap import dedent
from xml.etree import ElementTree

import pytest
from typer.testing import CliRunner

from entroping.cli.main import app


@pytest.mark.integration
@pytest.mark.regression
def test_cli_run_wires_discovery_gate_injection_fake_hurl_and_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "qanstitution.yaml").write_text(
        dedent(
            """\
            project: integration-project
            settings:
              timeout: 5000
              parallel_workers: 2
            gates:
              - id: latency
                condition: "true"
                gate: duration < 2000
                enforcement: block
            """
        ),
        encoding="utf-8",
    )
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    env_dir.joinpath("local.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    source = tests_dir / "health.hurl"
    source_content = "# entroping: tags=integration\n\nGET {{base_url}}/health\nHTTP 200\n"
    source.write_text(source_content, encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_hurl = fake_bin / "hurl"
    fake_hurl.write_text(
        dedent(
            """\
            #!/usr/bin/env python3
            import json
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            hurl_path = Path(args[-1]).resolve()
            content = hurl_path.read_text(encoding="utf-8")
            variables = ""
            if "--variables-file" in args:
                variables_path = Path(args[args.index("--variables-file") + 1])
                variables = variables_path.read_text(encoding="utf-8")
            state_dir = hurl_path.parent.parent
            state_dir.joinpath("fake-hurl-observation.json").write_text(
                json.dumps(
                    {
                        "argv": args,
                        "content": content,
                        "hurl_path": str(hurl_path),
                        "variables": variables,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            if "# entroping-gate: latency enforcement=block" not in content:
                print("missing injected latency gate", file=sys.stderr)
                raise SystemExit(7)
            if "duration < 2000" not in content:
                print("missing injected latency assertion", file=sys.stderr)
                raise SystemExit(8)
            if "GET {{base_url}}/health" not in content:
                print("missing original request", file=sys.stderr)
                raise SystemExit(9)
            gate_line = next(
                index + 2
                for index, line in enumerate(content.splitlines())
                if line.startswith("# entroping-gate:")
            )
            capture_name = next(
                line.split(":", maxsplit=1)[0]
                for line in content.splitlines()
                if line.startswith("__entroping_response_body_") and line.endswith(": bytes")
            )
            print(
                json.dumps(
                    {
                        "filename": str(hurl_path),
                        "success": True,
                        "entries": [
                            {
                                "asserts": [{"line": gate_line, "success": True}],
                                "calls": [
                                    {
                                        "response": {
                                            "status": 200,
                                            "headers": [
                                                {"name": "Content-Type", "value": "text/plain"},
                                            ],
                                        },
                                    },
                                ],
                                "captures": [
                                    {
                                        "name": capture_name,
                                        "value": "YmFzZV91cmw9aHR0cDovL2xvY2FsaG9zdDoxODA4MAo=",
                                    },
                                ],
                            },
                        ],
                    },
                ),
            )
            """
        ),
        encoding="utf-8",
    )
    fake_hurl.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{Path('/usr/bin')}:{Path('/bin')}")

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--env",
            "local",
            "--tag",
            "integration",
            "--report",
            "json",
            "--report",
            "junit",
        ],
    )

    assert result.exit_code == 0
    assert "Hurl run: 1 passed, 0 failed" in result.output
    assert source.read_text(encoding="utf-8") == source_content
    assert not list((tmp_path / ".entroping").glob("run-*"))

    observation = json.loads(
        (tmp_path / ".entroping" / "fake-hurl-observation.json").read_text(
            encoding="utf-8"
        )
    )
    assert observation["hurl_path"] != str(source.resolve())
    assert ".entroping" in Path(observation["hurl_path"]).parts
    assert observation["variables"] == "base_url=http://localhost:18080\n"
    assert "# entroping-gate: latency enforcement=block" in observation["content"]
    assert "duration < 2000" in observation["content"]

    report = json.loads((tmp_path / "reports" / "run-latest.json").read_text(encoding="utf-8"))
    latest = json.loads((tmp_path / ".entroping" / "latest-run.json").read_text(encoding="utf-8"))
    junit_root = ElementTree.parse(tmp_path / "reports" / "junit.xml").getroot()
    assert report == latest
    assert report["project"] == "integration-project"
    assert report["environment"] == "local"
    assert report["tests"][0]["path"] == "tests/health.hurl"
    assert report["tests"][0]["rule_ids"] == ["latency"]
    assert "http://localhost:18080" not in json.dumps(report)
    assert "base_url=[REDACTED]" in report["tests"][0]["stdout"]
    assert junit_root.attrib["tests"] == "1"
    assert junit_root.attrib["failures"] == "0"
