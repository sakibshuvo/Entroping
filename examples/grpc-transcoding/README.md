# gRPC HTTP-Transcoding Fixture

This fixture demonstrates a local proto contract that can drive an HTTP-backed
Hurl smoke scaffold. Entroping does not add a native gRPC streaming engine here;
the bridge treats proto metadata as input for reviewable HTTP regression checks.

## Files

```text
contracts/orders.proto
```

## Design Notes

- `contracts/orders.proto` includes `google.api.http` annotations for local
  HTTP-transcoding proof.
- Generated Hurl scaffolds use caller-provided target URLs and do not render
  proto service names, RPC names, HTTP annotation paths, request schemas, or
  response schemas.
- Native gRPC streaming remains future work.
