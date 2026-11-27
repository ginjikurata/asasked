# lab.asasked.dev — v1: stores that take crypto

A static Next.js page listing online stores where you can pay in crypto or stablecoins.
Same stack and look as `asasked-public/site` (Next.js 16, React 19, Tailwind v4).

- Data: `../research/merchants.csv` (not in the public repo). `npm run data` (runs before `dev` and `build`) writes
  `lib/merchants.json`, keeping only rows with `verified` = `yes` or `partial`. Without the CSV, the committed
  `lib/merchants.json` is the published list; run `next dev` / `next build` directly to skip the data step.
- No ads, no analytics. Filtering runs in the browser. The small Node server in `server/` handles wallet
  sign-in, the account page, chat and MCP; it sets one sign-in cookie.
- Search engines: `LAUNCHED` in `lib/site.ts` (open since 2026-11-28).
- Payment always happens on the store's own checkout; the site never touches money.
- No affiliate links yet. If added, each card must say so (see the "How we earn" block).
- Product search (Shopify UCP) is not in v1: Shopify API Terms §2.3.14 forbid a product index without consent.

```
npm install
npm run dev     # http://localhost:3100
npm run build
```

Deploy only after the owner says yes.
- Server (sign-in, profile, agents, MCP): the owner runs `sh deploy/api-install.sh` (root alias `concord`). It copies the server code to /opt/asasked-lab, sets up the systemd service `asasked-lab` (data in /var/lib/asasked-lab) and adds /api and /mcp to Caddy. Run it again after server changes.
- Static pages: `sh scripts/deploy.sh` (key `labdeploy`, only the site folder).
