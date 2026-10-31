import examples from "@/lib/examples.json";

/**
 * The whole idea at a glance, in the first screen: one real sandbox cart that passes Verifiable
 * Intent and gets stamped "ask". Same data as the first "Try it" example.
 */
export function HeroSlip() {
  const ex = examples[0];
  const item = ex.wrong.cart[0];
  const rows: [string, React.ReactNode][] = [
    ["asked", `“${ex.request}”`],
    ["cart", `${item.name} · ${item.merchant} · ${item.price} · ${item.returns}`],
    ["VI", <span key="vi" className="text-pass">✓ chain valid · constraints satisfied</span>],
    ["guard", <span key="g" className="font-medium text-signal">{ex.wrong.decision}: {ex.wrong.reasons[0].split(":")[0]}</span>],
  ];
  return (
    <figure className="receipt relative mt-8 px-4 pt-3 font-mono text-[12px] leading-relaxed md:text-[12.5px]">
      <dl className="space-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[52px_1fr] gap-3">
            <dt className="text-faint">{k}</dt>
            <dd className="pr-16">{v}</dd>
          </div>
        ))}
      </dl>
      <span className="stamp absolute right-4 top-1/2 -translate-y-1/2 text-signal">{ex.wrong.decision}</span>
    </figure>
  );
}
