# Checkout API Demo Fixture

This fixture is a tiny first-run example for Entroping's deterministic alpha loop.

It exists to reduce terminology friction: a new user should be able to see `qanstitution.yaml`, Hurl metadata comments, an OpenAPI source, and a test file in one place.

## Files

```text
demo_server.py
openapi.yaml
qanstitution.yaml
tests/checkout_smoke.hurl
tests/generated/
```

The installed `entroping demo` command creates `envs/local.env`, generated
tests, and `reports/` at runtime. The source-checkout fixture additionally
contains `envs/local.env.example`; it is not part of the package-safe copied
fixture.

## Quickstart

From the repository root:

```bash
uv sync --dev
brew install hurl
```

Terminal 1:

```bash
python examples/checkout-api/demo_server.py --port 18080
```

Terminal 2:

```bash
cd examples/checkout-api
uv run --project ../.. entroping doctor
uv run --project ../.. entroping run --tag smoke --report json --report junit
```

Expected result:

```text
Hurl run: 1 passed, 0 failed
Wrote latest run state: .entroping/latest-run.json
Wrote report: reports/run-latest.json
Wrote report: reports/junit.xml
```

To regenerate Hurl tests from `openapi.yaml`:

```bash
uv run --project ../.. entroping architect build --new --tag smoke
mkdir -p envs
printf 'base_url=http://127.0.0.1:18080\ncart_id=demo-cart-001\n' > envs/local.env
uv run --project ../.. entroping run --env local --tag smoke --report html --report json --report junit
```

## Launch Asset Generation

The public launch kit in `docs/assets/launch/README.md` is generated from this
fixture. From the repository root:

```bash
demo_tmp_base="${ENTROPING_DEMO_TMP_BASE:-$HOME/.cache/entroping-demo}"
mkdir -p "$demo_tmp_base"
artifact_dir="$(mktemp -d "$demo_tmp_base/artifacts.XXXXXX")"
workdir="$(mktemp -d "$demo_tmp_base/work.XXXXXX")"
ENTROPING_LIVE_DEMO_ARTIFACT_DIR="$artifact_dir" \
  ENTROPING_LIVE_DEMO_WORKDIR="$workdir" \
  scripts/demo.sh
```

Use `scripts/live_demo_smoke.sh` directly when you need the lower-level release
gate without wrapper messaging. Use the copied HTML, JSON, and JUnit reports as
screenshot sources. Keep the generated `reports/`, `.entroping/`, GIFs, and
PNGs out of Git unless a launch asset is intentionally curated and size-checked.

## Design Notes

- The example avoids real secrets.
- `smoke` tests should remain idempotent.
- Hurl metadata uses comments so the Hurl parser can safely ignore Entroping-specific data.
- The QAnstitution condition examples stay inside the supported small DSL.
- The demo server returns `X-Request-Id` so the first-hour request-ID header gate is runnable.
- The checked-in `.hurl` file uses a literal local URL so the alpha quickstart does not depend on environment-variable loading.
- Source checkouts may copy the safe `envs/local.env.example`; installed demos create the gitignored `envs/local.env` directly.
- Generated OpenAPI tests are written under `tests/generated/` and use `{{base_url}}` from `--env local`.
