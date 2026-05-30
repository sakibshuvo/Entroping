# Security Policy

## Reporting Vulnerabilities

Do not report sensitive vulnerabilities in a public issue. Use GitHub private vulnerability reporting:

```text
https://github.com/sakibshuvo/Entroping/security/advisories/new
```

If private reporting is unavailable, contact the maintainer privately and include only the minimum detail needed to establish impact.

## Supported Versions

Entroping is pre-1.0 alpha. Security fixes target the current `main` branch and the latest alpha tag when practical.

## Security Boundaries

High-risk areas include:

- Hurl subprocess execution.
- QAnstitution import and gate parsing.
- CLI path, glob, YAML, OpenAPI, and Hurl metadata inputs.
- mitmproxy traffic capture and redaction.
- Report generation and Markdown/HTML escaping.
- LiteLLM prompt construction and response parsing.
- Local `.entroping/state.db` persistence.

## Local Security Checks

Run:

```bash
scripts/regression.sh --security
```

This runs repo hygiene, linting, typing, tests, Bandit, default dependency audit, and all-extras dependency audit.
