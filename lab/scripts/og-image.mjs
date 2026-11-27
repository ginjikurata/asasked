// Makes public/og.png (1200x630), the picture shown when a lab link is shared. Run: node scripts/og-image.mjs
import sharp from "sharp";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const src = readFileSync(new URL("../lib/mark.ts", import.meta.url), "utf8");
const path = [...src.match(/MARK_PATH = \[([\s\S]*?)\] as const/)[1].matchAll(/\[(\d), (\d)\]/g)].map((m) => [+m[1], +m[2]]);
const end = src.match(/MARK_END = \[(\d), (\d)\]/).slice(1).map(Number);
const s = 30, ox = 96, oy = 96;
const px = path.map(([x, y]) => `<rect x="${ox + x * s}" y="${oy + y * s}" width="${s}" height="${s}" fill="#1b1a17"/>`).join("");
const font = "Helvetica Neue, Helvetica, Arial, sans-serif";
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#faf8f4"/>
${px}<rect x="${ox + end[0] * s}" y="${oy + end[1] * s}" width="${s}" height="${s}" fill="#e0371f"/>
<text x="${ox + 6 * s + 28}" y="${oy + 92}" font-family="${font}" font-size="44" font-weight="600" fill="#1b1a17">AsAsked <tspan font-weight="400" fill="#625d54">Lab</tspan></text>
<text x="96" y="356" font-family="${font}" font-size="88" font-weight="700" fill="#1b1a17" letter-spacing="-2">Shops that take crypto</text>
<text x="96" y="430" font-family="${font}" font-size="36" fill="#625d54">Each store checked one by one. You pay the store directly.</text>
<rect x="96" y="500" width="1008" height="2" fill="#e9e4da"/>
<text x="96" y="556" font-family="${font}" font-size="30" fill="#c22a14">lab.asasked.dev</text>
</svg>`;
await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile(fileURLToPath(new URL("../public/og.png", import.meta.url)));
console.log("public/og.png");
