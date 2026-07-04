# AI-regression proof

This fixture shows a realistic AI-assisted backend regression: a generated
handler still returns `200 OK` and the expected JSON body, but it drops the
`X-Request-Id` response header that operations depend on for debugging.

`scripts/ai_regression_demo.sh` starts this intentionally broken local API,
runs `entroping run --ci --tag ai-regression --report json`, and succeeds only
when Entroping blocks the regression through the `request_id_header` gate.

This is not a replacement for the happy-path checkout demo. It is a failure
proof that shows why executable policy matters even when the endpoint still
"looks fine" at the body/status level.

## Walkthrough

1. Run the fixture script:

   ```bash
   scripts/ai_regression_demo.sh
   ```

2. Observe that `entroping run --ci --tag ai-regression --report json` fails
   because the `request_id_header` gate blocks the intentionally missing
   `X-Request-Id` response header.

3. Use the generated `reports/run-latest.json` to confirm the guardrail failure
   is deterministic and replayable.
