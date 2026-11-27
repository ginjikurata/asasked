// Serves out/ like the live Caddy: /path → out/path.html, /path/ → 404. For local checks only.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const root = join(import.meta.dirname, "../out");
const port = Number(process.env.PORT ?? 3102);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".png": "image/png", ".woff2": "font/woff2", ".txt": "text/plain" };

const isFile = (p) => stat(p).then((s) => s.isFile(), () => false);

createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  const tries = path === "/" ? ["/index.html"] : path.endsWith("/") ? [] : [path, `${path}.html`];
  for (const t of tries) {
    const f = join(root, t);
    if (f.startsWith(root) && (await isFile(f))) {
      res.writeHead(200, { "content-type": types[extname(f)] ?? "application/octet-stream" });
      return res.end(await readFile(f));
    }
  }
  res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
  res.end(await readFile(join(root, "404.html")).catch(() => "Not found"));
}).listen(port, "127.0.0.1", () => console.log(`lab out/ on http://127.0.0.1:${port}`));
