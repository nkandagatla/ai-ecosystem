---
name: mobile-app-basics
description: Build and review mobile apps (React Native/Expo, Flutter, native iOS/Android) - navigation, offline state, permissions, accessibility, performance and store release. Use for mobile app work.
---

# Mobile app basics

- Pick one stack per app; follow its official project template and navigation library.
- State: server cache (React Query/Riverpod) separate from UI state; design for offline and flaky networks (retries, optimistic updates, conflict handling).
- Permissions: request just-in-time with a rationale screen; handle denial gracefully.
- Accessibility: labels on all controls, dynamic type, 44x44pt touch targets, screen reader pass on both platforms.
- Performance: avoid re-render storms, virtualize long lists, measure cold start; keep the JS/Dart thread free.
- Security: no secrets in the bundle; Keychain/Keystore for tokens; certificate pinning only with a rotation plan.
- Testing: unit + component tests, and an E2E smoke flow (Detox/Maestro/integration_test) on real devices or emulators in CI.
- Release: semver + build numbers, staged rollout, crash reporting, and a rollback (feature flag or expedited fix) plan.
