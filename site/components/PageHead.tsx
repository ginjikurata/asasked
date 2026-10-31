/**
 * The top of an inner page. It carries the ids the background reads (#hero, #hero-copy), so the
 * payment network grows into the bands above and below the title, as on the home page.
 */
export function PageHead({ kicker, title, children }: { kicker: string; title: string; children?: React.ReactNode }) {
  return (
    <section id="hero" className="column pb-20 pt-24 md:pb-28 md:pt-32">
      <div id="hero-copy">
        <p className="meta">{kicker}</p>
        <h1 className="mt-3 text-[40px] font-bold leading-[1.05] tracking-[-0.03em] md:text-[56px]">{title}</h1>
        {children && <div className="mt-6 text-[17px] leading-[1.65] md:text-lg">{children}</div>}
      </div>
    </section>
  );
}
