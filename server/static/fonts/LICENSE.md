# Bundled font

**Space Grotesk** by Florian Karsten — SIL Open Font License 1.1.

- Upstream: https://github.com/floriankarsten/space-grotesk
- License: https://openfontlicense.org/
- Files: `space-grotesk-latin.woff2`, `space-grotesk-latin-ext.woff2`
  (variable weight 300–700, subset to latin and latin-ext)

Self-hosted rather than loaded from a font CDN on purpose. This app serves one
person's private notes, so every third-party request is a referrer leak and an
availability dependency for no gain. It also keeps the Content-Security-Policy
tight enough to name `'self'` as the only font source.
