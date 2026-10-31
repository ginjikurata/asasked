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
| Texts, numbers, links | `lib/content.ts` — facts only, each checkable against this repository |
| Colours and fonts | `app/globals.css` (`@theme` tokens, dark mode under `prefers-color-scheme`) |
| Page | `app/page.tsx`; header, footer and the GitHub link in `components/Chrome.tsx` |
| Spec | `app/spec/page.tsx` renders `../spec/guard.md` at build time — the site and the spec cannot differ |
| Examples and open tasks | `lib/examples.json`, `lib/dataset-open.json`, written by `scripts/build_site_data.py` (open half only) |
| Background | `components/PixelField.tsx` (payment network), sprites in `lib/sprites.ts` |

**Before launch** `LAUNCHED = false`: the site sends `noindex` and `robots.txt` disallows
everything, and links to the code render as `[at launch]` until `GITHUB_URL` is set.
`RESULTS.preliminary` shows a note that model results are being re-run.

**At deploy:** `/legal` and `/privacy` say the site runs on the Concord server (UltaHost,
Frankfurt) with no request log, as concord.solutions does. Check that this is true for the
asasked.dev app before launch; `OPERATOR` in `lib/content.ts` holds those facts.
