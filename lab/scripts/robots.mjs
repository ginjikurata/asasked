// Minimal robots.txt: rules for our agent if listed, else for "*". Disallow prefixes only, Allow overrides longer-or-equal.
export function robotsRules(txt) {
  const groups = []; let cur = null;
  for (const raw of txt.split(/\r?\n/)) {
    const line = raw.replace(/#.*/, "").trim(); if (!line) continue;
    const [k, ...rest] = line.split(":"); const key = k.trim().toLowerCase(); const val = rest.join(":").trim();
    if (key === "user-agent") { if (!cur || cur.rules.length) { cur = { agents: [], rules: [] }; groups.push(cur); } cur.agents.push(val.toLowerCase()); }
    else if ((key === "disallow" || key === "allow") && cur) cur.rules.push({ allow: key === "allow", path: val });
  }
  const mine = groups.find((g) => g.agents.some((a) => a && "asaskedlabbot".includes(a) && a !== "*"));
  return (mine ?? groups.find((g) => g.agents.includes("*")))?.rules ?? [];
}
export function allowed(rules, path) {
  let best = null;
  for (const r of rules) {
    if (!r.path) continue;
    const p = r.path.replace(/\*$/, "");
    if (p.includes("*") ? new RegExp("^" + p.split("*").map((s) => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*")).test(path) : path.startsWith(p.replace(/\$$/, ""))) {
      if (!best || p.length > best.len || (p.length === best.len && r.allow)) best = { len: p.length, allow: r.allow };
    }
  }
  return best ? best.allow : true;
}
