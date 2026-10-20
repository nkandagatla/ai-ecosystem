# ADR 0001: Plain static HTML/CSS

- Status: accepted
- Context: one page, no dynamic data, must be fast and cheap to host.
- Decision: a single `index.html` with inline CSS; no framework or build step. Host on any static host (GitHub Pages / S3+CloudFront).
- Consequences: zero build tooling and instant loads; if a menu CMS is needed later, revisit (Astro or similar).
