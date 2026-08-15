---
title: ADR-0034 HTTP API Breadth Selector Boundary
type: decision
status: accepted
date: 2026-08-14
tags:
  - bridge
  - http-api
  - selectors
  - internal-scaffold
---

# ADR-0034: HTTP API Breadth Selector Boundary

## Decision

`graphql_to_hurl.py`, `soap_to_hurl.py`, `asyncapi_to_hurl.py`, and
`proto_to_hurl.py` are internal v4.1 scaffolds with no public command/config/help
expansion.

- selectors are strict keyword-only strings with no regex/glob/expression semantics.
- grammars: `query_field` `[_A-Za-z][_0-9A-Za-z]{0,127}`,
  `operation_name` `[A-Za-z_][A-Za-z0-9_.-]{0,127}`,
  `channel`+`operation`, `rpc_name` `[A-Za-z_][A-Za-z0-9_]{0,127}`.
- omitted selectors preserve baseline; selected mode returns one immutable typed artifact
  (`GeneratedGraphqlHurlFile`, `GeneratedSoapHurlFile`,
  `GeneratedAsyncapiWebhookHurlFile`, or `GeneratedProtoHurlFile`) and validates all
  selection before return; on failure returns no artifact.
- errors are exactly `GraphqlHurlCompilationError`, `SoapHurlCompilationError`,
  `AsyncapiHurlCompilationError`, `ProtoHurlCompilationError`, all `ValueError`
  subclasses.
- selection failures are fixed-category; security/resource failures are content-free.
- empty, whitespace, control, secret-like, and missing/unsafe `target_url` inputs fail
  before output without echoing attacker data.
- compilers perform no provider/network/schema fetch, no `hurl` execution, no writes;
  caller persistence is outside compiler authority.

## GraphQL selector

`compile_graphql_sdl_to_hurl(schema_sdl: str, *, target_url: str, query_field: str | None = None)`

- `query_field` omitted: exact baseline `query EntropingSmoke { __typename }` bytes.
- compile target requires one canonical base `type Query` + zero+extend blocks; selected
  field must match once globally, zero-argument, and directive-free.
- selected mode renders `query EntropingSmoke { <query_field> }`; baseline headers, method,
  path metadata, and `jsonpath "$.errors" not exists` assertion remain unchanged.
- happy: `query_field="viewer"` with one canonical `viewer` field.
- fail if missing/empty/ambiguous selector, non-Query field set, or non-GraphQL-name text.

## SOAP selector

`compile_wsdl_to_soap_hurl(wsdl_xml: str, *, target_url: str, operation_name: str | None = None)`

- root namespace: exact `http://schemas.xmlsoap.org/wsdl/`.
- operation selection: one local `portType` operation, one matching SOAP binding operation,
  one non-empty `soapAction`; no include/import; no SOAP 1.2.
- omitted `operation_name`: exact baseline SOAP smoke.
- selected mode injects fixed request element `ent:EntropingSmokeRequest` with quoted,
  safely escaped `soapAction`; no attacker-derived QName or body is rendered.
- happy: one exact local operation with one exact action.
- fail if missing/ambiguous operation or action, or unsafe metadata/selector.

## AsyncAPI selector

`compile_asyncapi_webhook_to_hurl(asyncapi_yaml: str, *, target_url: str, channel: str | None = None, operation: Literal["publish", "subscribe"] | None = None)`

- AsyncAPI 2.x only.
- either both `channel` and `operation` are supplied or both omitted.
- `channel` is exact `channels` map key and exact request path; for this subset it must be
  UTF-8 absolute path 1..1024 bytes beginning `/`, segments `[A-Za-z0-9._~-]+`, and reject
  `//`, traversal, query/fragment, percent-encoding, braces, controls, and unsafe/secret-like
  values.
- `channels[channel].bindings.http` must be present, empty, and only the webhook marker.
  The operation method and metadata come from `channels[channel][operation].bindings.http` only.
- operation binding must include exactly one `method` and optional `bindingVersion=0.3.0`, and
  only keys `method`/`bindingVersion`; unknown keys rejected.
- allowed methods: GET/POST/PUT/PATCH/DELETE.
- `query` binding is rejected; non-HTTP/malformed operation/channel binding fail.
- selected output joins the validated `target_url` origin with the channel path; target
  path/query/fragment and binding path data are ignored. POST/PUT/PATCH emit fixed
  value-free JSON; GET/DELETE emit no body. Schema/examples are never materialized.
- selected publish/subscribe operation/binding absent/ambiguous -> fail; one exact match
  renders one output.
- happy: `channel="/orders"`, `operation="publish"` with one HTTP binding.
- fail if missing/ambiguous selected operation/binding, invalid `bindingVersion`, unsafe `channel`,
  invalid method, or unsafe metadata.

## Proto selector

`compile_proto_http_transcoding_to_hurl(proto_text: str, *, target_url: str, rpc_name: str | None = None)`

- omitted `rpc_name`: exact HTTP-transcoding baseline preserved.
- select one unary, non-streaming `rpc` with one primary `google.api.http`.
- primary path is absolute ASCII 1..1024, placeholders only `{field}` / `{field.path}` with
  `[A-Za-z_][A-Za-z0-9_]*`; reject `=`, `*`, percent-encoding, query, fragment,
  authority, dot-segment, traversal, controls, and secret-like values.
- output path joins `target_url` origin and replaces placeholders with fixed `entroping`.
- selected body policy: GET/DELETE forbid body; POST/PUT/PATCH require exact `body: "*"`;
  those mutating methods emit fixed value-free JSON; other methods fail.
- happy: `rpc_name="GetOrder"` with one matching GET rule emits deterministic output.
- fail if missing/ambiguous candidates, custom verb, additional_bindings, duplicate primary,
  streaming RPC, invalid body/metadata/path, or unsafe selectors.

## Non-goals

- CLI surface expansion.
- runtime execution, provider/network access, schema fetch, or compiler write authority.
- schema/example payload materialization.

## References

- `decisions/ADR-0002-locked-command-surface.md`
- `docs/product/PRODUCT_SPEC.md`
- `docs/technical/SURFACE_SCOPE.md`
- `docs/technical/TDS.md`
- `https://github.com/asyncapi/bindings/tree/master/http`
