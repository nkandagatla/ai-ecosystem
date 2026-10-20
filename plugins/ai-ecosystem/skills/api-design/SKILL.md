---
name: api-design
description: Design and review HTTP/REST and event APIs - resources, versioning, errors, pagination, auth and OpenAPI contracts. Use when creating or changing an API endpoint or contract.
---

# API design

1. Contract first: write or update `openapi.yaml` (or AsyncAPI for events) before code; review it with the architect.
2. Resources are nouns, plural, kebab-case (`/order-items/{id}`); use HTTP verbs for actions; avoid RPC-style URLs unless the action is not CRUD.
3. Status codes: 200/201/204 success, 400 validation, 401 unauthenticated, 403 forbidden, 404 missing, 409 conflict, 422 semantic error, 429 rate limited, 5xx server.
4. Errors use one shape everywhere (RFC 9457 `application/problem+json`: `type`, `title`, `status`, `detail`, `instance`).
5. Pagination: cursor-based (`?cursor=&limit=`) with `next` links; cap `limit`.
6. Versioning: additive changes only within a version; breaking changes get a new version (`/v2` or media type) plus a deprecation window.
7. Security: authn on every endpoint, authz per resource, validate all input against the schema, idempotency keys for unsafe retries, no secrets or PII in URLs/logs.
8. Verify: contract tests (e.g. Schemathesis/Dredd) in CI; generate clients from the spec.
