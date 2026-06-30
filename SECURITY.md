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

## QAnstitution Policy Change Review

QAnstitution files and related policy implementation paths define the
deterministic governance that Entroping enforces before API behavior is trusted.
`.github/CODEOWNERS` routes changes to those paths to `@sakibshuvo`, including
`qanstitution.yaml`, policy-pack examples, the QAnstitution reference/schema,
the typed models, the loader, and policy-to-Hurl compilation.

CODEOWNERS routing does not prove branch protection is enabled. Maintainers must
configure GitHub branch protection for protected branches so it requires code
owner review on pull requests before treating that owner mapping as enforced
policy. Without that repository setting, the file is review-routing guidance,
not an active merge gate.

## Local Security Checks

Run:

```bash
scripts/regression.sh --security
```

This runs repo hygiene, linting, typing, tests, Bandit, default dependency audit, and all-extras dependency audit.

## Public Trust Signals

The repository includes community-health files and a non-blocking OpenSSF
Scorecard workflow:

```bash
scripts/community_profile_audit.sh
```

`.github/workflows/scorecard.yml` runs on a weekly schedule or manual dispatch,
publishes Scorecard results for the README badge, and is intentionally not a
pull-request gate.
