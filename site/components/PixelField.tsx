"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BANK, SPRITES, pixels, type Sprite } from "@/lib/sprites";

/**
 * Page background: a 1-bit pixel payment network down the whole page, in the margins either side
 * of the text column and in the bands above and below the intro. The column itself stays white.
 *
 * Hubs are the pieces of a purchase — cart, agent, card, terminal, receipt, bank — joined by
 * right-angled traces that route around other hubs, with stubs ending in pads. Payments run along
 * the traces. The cursor is the guard: a payment passing close to it turns red and stops, and a
 * question lights up where it stopped. Most payments arrive and a check blinks; now and then one
 * is asked about on its own.
 *
 * Rendering is exact: one field pixel is a whole number of device pixels, the field scrolls with
 * the page to the device pixel, and nothing is scaled by the browser.
 */

const PX = 3;                // target size of one field pixel, CSS px
const PAYMENTS = 7;          // payments in flight near the screen
const SPEED = 38;            // cells per second
const GUARD_RADIUS = 9;      // cells around the cursor where a payment is stopped
const SELF_ASK = 0.12;       // share of arrivals the guard asks about with no cursor near
const AIR = 3;               // empty cells kept around every hub
export const REPRINT_EVENT = "asasked:reprint";

type Cellxy = [number, number];
type Hub = { sprite: Sprite; x: number; y: number; w: number; h: number };
type Trace = Cellxy[];
type Dot = { x0: number; y0: number; x: number; y: number; vx: number; vy: number; ph: number };
type Field = { ink: number[][]; red: number[][]; traces: Trace[]; dots: Dot[] };
type Payment = { trace: Trace; at: number; stopped: number };
type Flash = { sprite: Sprite; x: number; y: number; until: number };

const PIECES = SPRITES.filter((s) => s.name !== "ask" && s.name !== "check");
const ASK = SPRITES.find((s) => s.name === "ask")!;
const CHECK = SPRITES.find((s) => s.name === "check")!;

function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function grow(
  w: number, h: number, seed: number, ex: [number, number], heroH: number, tb: [number, number], headH: number,
): Field {
  const r = rng(seed);
  const pick = <T,>(a: T[]) => a[Math.floor(r() * a.length)];
  // the text column stays white wherever text sits; in the hero, the bands above and below the intro fill too
  const clear = (x: number, y: number) => x > ex[0] && x < ex[1] && (y > heroH || (y >= tb[0] && y <= tb[1]));
  const ink: number[][] = Array.from({ length: h }, () => []);
  const red: number[][] = Array.from({ length: h }, () => []);
  const used = new Set<number>();     // every inked cell
  const reserved = new Set<number>(); // hub boxes with their air: traces, stubs and dots keep out
  const traces: Trace[] = [];
  const dots: Dot[] = [];
  const hubs: Hub[] = [];
  const key = (x: number, y: number) => y * w + x;
  const inside = (x: number, y: number) => x >= 0 && y >= 0 && x < w && y < h && !clear(x, y);
  const put = (x: number, y: number, isRed = false) => {
    if (!inside(x, y) || used.has(key(x, y))) return;
    used.add(key(x, y));
    (isRed ? red : ink)[y].push(x);
  };
  const free = (x: number, y: number) => inside(x, y) && !reserved.has(key(x, y));

  // a hub: a sprite drawn at 1× or 2× (each sprite pixel a 2×2 block), with empty air around it
  function place(sprite: Sprite, cx: number, cy: number, scale = 1): Hub | null {
    const sw = sprite.rows[0].length * scale;
    const sh = sprite.rows.length * scale;
    const x0 = Math.round(cx - sw / 2);
    const y0 = Math.round(cy - sh / 2);
    for (let y = y0 - AIR - 2; y < y0 + sh + AIR + 2; y++) {
      for (let x = x0 - AIR - 2; x < x0 + sw + AIR + 2; x++) if (!free(x, y)) return null;
    }
    for (let y = y0 - AIR; y < y0 + sh + AIR; y++) for (let x = x0 - AIR; x < x0 + sw + AIR; x++) reserved.add(key(x, y));
    for (const [x, y, isRed] of pixels(sprite)) {
      for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) put(x0 + x * scale + dx, y0 + y * scale + dy, isRed);
    }
    const hub = { sprite, x: x0, y: y0, w: sw, h: sh };
    hubs.push(hub);
    return hub;
  }

  const ownAir = (hb: Hub, x: number, y: number) =>
    x >= hb.x - AIR && x < hb.x + hb.w + AIR && y >= hb.y - AIR && y < hb.y + hb.h + AIR;

  // the cells a right-angled route takes: down from a, across at `mid`, then into b from above,
  // or, when b sits beside a rather than below it, up into b from underneath
  function route(a: Hub, b: Hub, mid: number, under: boolean): Trace | null {
    const ax = a.x + Math.floor(a.w / 2);
    const ay = a.y + a.h;
    const bx = b.x + Math.floor(b.w / 2);
    const by = under ? b.y + b.h : b.y - 1;
    const path: Trace = [];
    const step = (from: number, to: number) => (to >= from ? 1 : -1);
    for (let y = ay; y !== mid; y += step(ay, mid)) path.push([ax, y]);
    for (let x = ax; x !== bx; x += step(ax, bx)) path.push([x, mid]);
    for (let y = mid; y !== by; y += step(mid, by)) path.push([bx, y]);
    path.push([bx, by]);
    // the ends leave and enter their own hubs' air; everywhere else the route must be clear
    const ok = path.every(([x, y]) => inside(x, y) && (!reserved.has(key(x, y)) || ownAir(a, x, y) || ownAir(b, x, y)));
    return ok && path.length >= 6 ? path : null;
  }

  // stubs off a trace, ending in a hollow pad: other routes the payment did not take
  function stubs(path: Trace, every: number) {
    for (let s = 0; s < path.length / every; s++) {
      const i = 2 + Math.floor(r() * (path.length - 4));
      const [sx, sy] = path[i];
      const [px] = path[i - 1];
      const along = px !== sx ? "x" : "y"; // stubs leave at a right angle to the trace
      const dir = r() < 0.5 ? -1 : 1;
      const len = 3 + Math.floor(r() * 7);
      const cells: Cellxy[] = [];
      for (let k = 1; k <= len + 3; k++) {
        const c: Cellxy = along === "x" ? [sx, sy + dir * k] : [sx + dir * k, sy];
        if (!free(c[0], c[1]) || used.has(key(c[0], c[1]))) break;
        cells.push(c);
      }
      if (cells.length < len + 3) continue; // no room for the stub and its pad: skip it
      cells.slice(0, len).forEach(([x, y]) => put(x, y));
      viaAt(cells[len - 1], along === "x" ? [0, dir] : [dir, 0]);
    }
  }

  // a 3×3 hollow pad just past `end`, in direction `d`
  function viaAt([x, y]: Cellxy, [dx, dy]: Cellxy) {
    const ox = dx > 0 ? x + 1 : dx < 0 ? x - 3 : x - 1;
    const oy = dy > 0 ? y + 1 : dy < 0 ? y - 3 : y - 1;
    for (let j = 0; j < 3; j++) for (let i = 0; i < 3; i++) if (i !== 1 || j !== 1) put(ox + i, oy + j);
  }

  function draw(path: Trace, dashed: boolean) {
    path.forEach(([x, y], i) => {
      if (!dashed || i % 3 !== 2) put(x, y);
    });
  }

  function connect(a: Hub, b: Hub, dashed = r() < 0.25): boolean {
    if (b.y < a.y) [a, b] = [b, a];
    const lo = a.y + a.h + AIR + 1;
    const hi = b.y - AIR - 2;
    const under = hi < lo;
    const floor = Math.max(a.y + a.h, b.y + b.h) + AIR + 2;
    let path: Trace | null = null;
    for (let tryNo = 0; tryNo < 8 && !path; tryNo++) {
      const mid = under ? floor + Math.floor(r() * 6) : Math.round(lo + (hi - lo) * r());
      path = route(a, b, mid, under);
    }
    if (!path) return false;
    draw(path, dashed);
    traces.push(path);
    stubs(path, 18);
    return true;
  }

  // a route that leads nowhere yet: down from a hub, ending in a pad
  function dangle(a: Hub) {
    const x = a.x + Math.floor(a.w / 2);
    const len = 8 + Math.floor(r() * 18);
    const path: Trace = [];
    for (let y = a.y + a.h; y < a.y + a.h + len; y++) {
      if (!inside(x, y) || (reserved.has(key(x, y)) && !ownAir(a, x, y))) return;
      path.push([x, y]);
    }
    draw(path, false);
    viaAt(path[path.length - 1], [0, 1]);
    stubs(path, 10);
  }

  // dust near a hub, kept off ink and off every hub's air
  function scatter(hub: Hub, n: number) {
    const cx = hub.x + hub.w / 2;
    const cy = hub.y + hub.h / 2;
    for (let k = 0; k < n; k++) {
      const a = r() * Math.PI * 2;
      const dist = Math.max(hub.w, hub.h) / 2 + AIR + 2 + Math.pow(r(), 1.4) * 18;
      const x = Math.round(cx + Math.cos(a) * dist);
      const y = Math.round(cy + Math.sin(a) * dist * 0.8);
      let near = false;
      for (let dy = -1; dy <= 1 && !near; dy++) for (let dx = -1; dx <= 1; dx++) if (used.has(key(x + dx, y + dy))) near = true;
      if (!near && free(x, y)) dots.push({ x0: x, y0: y, x, y, vx: 0, vy: 0, ph: r() * 6.28 });
    }
  }

  // a station: two to four hubs close together, one of them often big, wired as a little tree
  function station(x0: number, x1: number, y: number, size: number): Hub[] {
    const out: Hub[] = [];
    const width = x1 - x0;
    const big = width > 70 && r() < 0.5;
    const rootSprite = r() < 0.18 ? BANK : pick(PIECES);
    const root = place(rootSprite, x0 + width * (0.3 + r() * 0.4), y, big ? 2 : 1);
    if (!root) return out;
    out.push(root);
    for (let i = 1; i < size; i++) {
      for (let tryNo = 0; tryNo < 30; tryNo++) {
        const cx = x0 + 8 + r() * (width - 16);
        const cy = root.y + root.h / 2 + (r() - 0.3) * (big ? 80 : 60);
        const hub = place(pick(PIECES), cx, cy);
        if (!hub) continue;
        // wire it to the nearest hub already in the station
        const near = out.reduce((p, q) =>
          Math.hypot(q.x - hub.x, q.y - hub.y) < Math.hypot(p.x - hub.x, p.y - hub.y) ? q : p);
        connect(near, hub);
        out.push(hub);
        break;
      }
    }
    return out;
  }

  // down each margin: stations, lone pieces and empty stretches, so the rhythm is uneven
  for (const left of [true, false]) {
    const x0 = left ? 2 : ex[1] + 2;
    const x1 = left ? ex[0] - 2 : w - 2;
    if (x1 - x0 < 26) continue;
    let prev: Hub | null = null;
    for (let y = headH + 18 + r() * 30; y < h - 30; ) {
      const roll = r();
      if (roll < 0.25) {
        y += 60 + r() * 70; // nothing here
        prev = null;
        continue;
      }
      const group = roll < 0.45
        ? (() => {
            const hub = place(pick(PIECES), x0 + (x1 - x0) * (0.25 + r() * 0.5), y);
            if (hub) dangle(hub);
            return hub ? [hub] : [];
          })()
        : station(x0, x1, y, 2 + Math.floor(r() * 3));
      if (group.length) {
        if (prev && r() < 0.55) connect(prev, group[0], true); // a long-haul link, dotted
        prev = group.reduce((p, q) => (q.y + q.h > p.y + p.h ? q : p));
        y = prev.y + prev.h + 24 + r() * 40;
      } else {
        y += 20;
      }
    }
  }

  // across the intro: hubs in the bands above and below the text, on a shared bus
  const bands = [[headH, tb[0]], [tb[1], heroH]].filter(([a, b]) => b - a > 24);
  for (const [a, b] of bands) {
    const group: Hub[] = [];
    const n = Math.max(2, Math.round((ex[1] - ex[0]) / 50));
    for (let i = 0; i < n; i++) {
      if (r() < 0.2) continue; // leave a gap in the row
      const x = ex[0] + ((i + 0.5) / n) * (ex[1] - ex[0]) + (r() - 0.5) * 14;
      const hub = place(pick(PIECES), x, a + (b - a) * (0.3 + r() * 0.4));
      if (hub) group.push(hub);
    }
    group.sort((p, q) => p.x - q.x);
    for (let i = 1; i < group.length; i++) if (r() < 0.8) connect(group[i - 1], group[i]);
  }

  for (const hub of hubs) scatter(hub, 3 + Math.floor(r() * 7));
  return { ink, red, traces, dots };
}

export function PixelField() {
  const ref = useRef<HTMLCanvasElement>(null);
  const [seed, setSeed] = useState(7);
  const pathname = usePathname(); // a new page has a new hero and length: lay the field out again
  // each page grows its own network; "reprint" replaces it with a random one
  const pageSeed = [...pathname].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

  useEffect(() => {
    // the entry screen lifts by CSS; background tabs can stall that animation, so lift it here too
    const lift = window.setTimeout(() => document.documentElement.classList.add("gate-lifted"), 1800);
    const onReprint = () => setSeed((Math.random() * 1e9) | 0);
    window.addEventListener(REPRINT_EVENT, onReprint);
    return () => {
      window.clearTimeout(lift);
      window.removeEventListener(REPRINT_EVENT, onReprint);
    };
  }, []);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // geometry: `cell` is one field pixel in device pixels (a whole number), `css` the same in CSS px
    let dpr = 1, cell = PX, css = PX;
    let w = 0, h = 0, rowsOnScreen = 0, docH = 0, heroH = 0, t = 0, raf = 0, last = 0;
    let ex: [number, number] = [0, 0];
    let tb: [number, number] = [0, 0];
    let field: Field | null = null;
    let ink = "", red = "", paper = "";
    let mouse = { x: -1e4, y: -1e4 };
    let pointer: { x: number; y: number } | null = null;
    let payments: Payment[] = [];
    let flashes: Flash[] = [];

    function size() {
      const cs = getComputedStyle(document.documentElement);
      ink = cs.getPropertyValue("--color-ink").trim();
      red = cs.getPropertyValue("--color-signal").trim();
      paper = cs.getPropertyValue("--color-paper").trim();
      dpr = window.devicePixelRatio || 1;
      cell = Math.max(1, Math.round(PX * dpr));
      css = cell / dpr;
      // clientWidth, not innerWidth: the scrollbar is not page
      const cw = document.documentElement.clientWidth;
      const ch = window.innerHeight;
      canvas!.width = Math.ceil(cw * dpr);
      canvas!.height = Math.ceil(ch * dpr);
      canvas!.style.width = `${canvas!.width / dpr}px`;
      canvas!.style.height = `${canvas!.height / dpr}px`;
      w = Math.ceil(cw / css);
      rowsOnScreen = Math.ceil(ch / css) + 2;
      docH = document.documentElement.scrollHeight;
      h = Math.ceil(docH / css);
      const copy = document.getElementById("hero-copy");
      const col = (copy ?? document.body).getBoundingClientRect();
      const gap = 26;
      ex = [Math.floor((col.left - gap) / css), Math.ceil((col.right + gap) / css)];
      const hero = document.getElementById("hero");
      heroH = hero ? Math.ceil((hero.getBoundingClientRect().bottom + window.scrollY) / css) : 0;
      tb = [Math.floor((col.top + window.scrollY - 22) / css), Math.ceil((col.bottom + window.scrollY + 22) / css)];
      const header = document.querySelector("header");
      const headH = Math.ceil(((header?.getBoundingClientRect().bottom ?? 0) + 8) / css);
      field = grow(w, h, seed === 7 ? pageSeed : seed, ex, heroH, tb, headH);
      payments = [];
      flashes = [];
      draw();
    }

    function draw() {
      if (!field) return;
      // scroll to the device pixel, so the field moves with the text instead of in 3px steps
      const scroll = Math.round(window.scrollY * dpr);
      const top = Math.floor(scroll / cell);
      const shift = scroll - top * cell;
      const at = (x: number, y: number, n = 1) => ctx!.fillRect(x * cell, (y - top) * cell - shift, cell * n, cell * n);
      ctx!.clearRect(0, 0, canvas!.width, canvas!.height);
      const y0 = Math.max(0, top);
      const y1 = Math.min(h, top + rowsOnScreen);
      ctx!.fillStyle = ink;
      for (let y = y0; y < y1; y++) for (const x of field.ink[y]) at(x, y);
      for (const d of field.dots) if (d.y >= y0 - 2 && d.y <= y1 + 2) at(Math.round(d.x), Math.round(d.y));
      ctx!.fillStyle = red;
      for (let y = y0; y < y1; y++) for (const x of field.red[y]) at(x, y);
      // payments in flight: a 3×3 block on the trace, red once the guard has stopped it
      for (const p of payments) {
        const [x, y] = p.trace[Math.min(p.trace.length - 1, Math.floor(p.at))];
        ctx!.fillStyle = p.stopped ? red : ink;
        at(x - 1, y - 1, 3);
      }
      // flashes sit on paper, so lines behind them do not show through
      for (const f of flashes) {
        const fw = f.sprite.rows[0].length;
        const fh = f.sprite.rows.length;
        ctx!.fillStyle = paper;
        ctx!.fillRect((f.x - 1) * cell, (f.y - 1 - top) * cell - shift, (fw + 2) * cell, (fh + 2) * cell);
        for (const [sx, sy, isRed] of pixels(f.sprite)) {
          ctx!.fillStyle = isRed ? red : ink;
          at(f.x + sx, f.y + sy);
        }
      }
    }

    function step(now: number) {
      if (!field) return;
      const dt = Math.min(0.1, (now - (last || now)) / 1000);
      last = now;
      t += dt;
      const top = window.scrollY / css;
      if (pointer) mouse = { x: pointer.x / css, y: top + pointer.y / css };

      // keep a few payments running on traces near the screen
      const near = field.traces.filter((tr) => tr.some(([, y]) => y > top - 20 && y < top + rowsOnScreen + 20));
      while (near.length && payments.length < PAYMENTS) {
        payments.push({ trace: near[Math.floor(Math.random() * near.length)], at: 0, stopped: 0 });
      }
      for (const p of payments) {
        if (p.stopped) continue;
        p.at += SPEED * dt;
        const [x, y] = p.trace[Math.min(p.trace.length - 1, Math.floor(p.at))];
        // the cursor is the guard: a payment passing close is stopped and asked about
        if ((x - mouse.x) ** 2 + (y - mouse.y) ** 2 < GUARD_RADIUS ** 2) {
          p.stopped = now + 1400;
          flashes.push({ sprite: ASK, x: x + 4, y: y - 15, until: now + 1400 });
        } else if (p.at >= p.trace.length - 1) {
          const ask = Math.random() < SELF_ASK;
          const s = ask ? ASK : CHECK;
          flashes.push({ sprite: s, x: x + 4, y: y - s.rows.length - 3, until: now + (ask ? 1400 : 700) });
          p.at = -1; // done
        }
      }
      payments = payments.filter((p) => p.at >= 0 && (!p.stopped || now < p.stopped));
      flashes = flashes.filter((f) => now < f.until);

      // loose dots sway and scatter from the cursor
      for (const d of field.dots) {
        if (d.y0 < top - 40 || d.y0 > top + rowsOnScreen + 40) continue;
        const dx = d.x - mouse.x;
        const dy = d.y - mouse.y;
        const dd = dx * dx + dy * dy;
        if (dd < 400) {
          const f = ((400 - dd) / 400) * 0.9;
          d.vx += (dx / Math.sqrt(dd + 1)) * f;
          d.vy += (dy / Math.sqrt(dd + 1)) * f;
        }
        d.vx += (d.x0 + Math.sin(t + d.ph) * 1.2 - d.x) * 0.02;
        d.vy += (d.y0 + Math.cos(t * 0.8 + d.ph) * 1.2 - d.y) * 0.02;
        d.vx *= 0.86;
        d.vy *= 0.86;
        d.x += d.vx;
        d.y += d.vy;
        if (d.x > ex[0] && d.x < ex[1] && (d.y > heroH || (d.y >= tb[0] && d.y <= tb[1]))) {
          d.x = d.x0;
          d.y = d.y0;
          d.vx = d.vy = 0;
        }
      }
      draw();
      raf = requestAnimationFrame(step);
    }

    size();
    const onScroll = () => draw();
    const onMove = (e: PointerEvent) => {
      pointer = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    if (!reduce) {
      raf = requestAnimationFrame(step);
      window.addEventListener("pointermove", onMove, { passive: true });
    }
    let timer = 0;
    const later = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(size, 200);
    };
    window.addEventListener("resize", later);
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", later);
    // zooming changes devicePixelRatio: lay the field out again on the new pixel grid
    const zoom = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
    zoom.addEventListener("change", later);
    // the page settles after fonts load; lay the network out again to cover it
    const ro = new ResizeObserver(() => {
      if (Math.abs(document.documentElement.scrollHeight - docH) > 120) later();
    });
    ro.observe(document.body);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(timer);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("resize", later);
      scheme.removeEventListener("change", later);
      zoom.removeEventListener("change", later);
      ro.disconnect();
    };
  }, [seed, pathname, pageSeed]);

  return <canvas ref={ref} aria-hidden className="pointer-events-none fixed left-0 top-0 -z-10" />;
}

/** The "reprint" link: lays out a new network. */
export function ReprintButton() {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new Event(REPRINT_EVENT))}
      className="meta text-signal underline underline-offset-4"
    >
      reprint
    </button>
  );
}
