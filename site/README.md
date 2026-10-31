# asasked.dev

The AsAsked site, static: `/` (home), `/spec`, `/docs`, `/dataset`, `/about`, `/changelog`,
`/legal`, `/privacy` and a 404.

Stack as on concord.solutions: Next.js 16 (App Router, Cache Components), React 19,
Tailwind CSS v4, TypeScript. Fonts (IBM Plex Sans, IBM Plex Mono) are self-hosted through
`next/font`, so visitors make no requests to Google.

```bash
npm ci
npm run dev        # http://localhost:3000
npm run build && npm run start
```

| What | Where |
| --- | --- |
| Texts, numbers, links | `lib/content.ts` — facts only, each checkable against this repository; `GITHUB_URL`, `PYPI_URL` and `VERSION` (keep it equal to `pyproject.toml`) |
| Install commands | `app/docs/page.tsx`, copied from `../README.md` and `../docs/install.md` — change them together |
| Colours and fonts | `app/globals.css` (`@theme` tokens, dark mode under `prefers-color-scheme`) |
| Page | `app/page.tsx`; header, footer and the GitHub link in `components/Chrome.tsx` |
| Spec | `app/spec/page.tsx` renders `../spec/guard.md` at build time — the site and the spec cannot differ |
| Examples and open tasks | `lib/examples.json`, `lib/dataset-open.json`, written by `scripts/build_site_data.py` (open half only) |
| Background | `components/PixelField.tsx` (payment network), sprites in `lib/sprites.ts` |

**Launched** on 31 October 2026: `LAUNCHED = true`, so pages are indexable and `robots.txt`
points to `sitemap.xml`. Setting it back to `false` hides the site from search engines again.
`RESULTS.preliminary` shows a note that model results are being re-run.

**At deploy:** `/legal` and `/privacy` say the site runs on the Concord server (UltaHost,
Frankfurt) with no request log, as concord.solutions does. Check that this is true for the
asasked.dev app before launch; `OPERATOR` in `lib/content.ts` holds those facts.
