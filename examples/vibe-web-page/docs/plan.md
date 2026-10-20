# Plan: coffee shop landing page

## Goal
A single responsive page that converts visitors into walk-ins and online orders.

## User stories
1. As a visitor I see opening hours and location above the fold. *AC:* hours + map link visible at 375px without scrolling.
2. As a visitor I can view the menu highlights. *AC:* 6 items with price; readable at 200% zoom.
3. As a visitor I can order online. *AC:* primary CTA links to the ordering URL; keyboard focus visible.

## Non-functional
Lighthouse performance and accessibility >= 90; no third-party JS; < 100 KB total.

## Out of scope
Online payments, CMS, analytics.

## Review / test / security log
- reviewer: approve (nit: extract colours into CSS custom properties - done).
- tester: AC 1-3 verified at 375/768/1280px; keyboard-only pass.
- security: static page, no forms or third-party scripts; CSP meta added.
