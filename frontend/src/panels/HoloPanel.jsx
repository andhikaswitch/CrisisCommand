// The core reusable holographic panel — UI_DESIGN.md §3 spec exactly.
// Every panel in the app uses this; never invent one-off panel styles.
export default function HoloPanel({ title, icon, children, style, className = '' }) {
  return (
    <section className={`holo-panel ${className}`} style={style}>
      <span className="holo-corner tl" />
      <span className="holo-corner tr" />
      <span className="holo-corner bl" />
      <span className="holo-corner br" />
      {title && (
        <header className="holo-title">
          {icon && <span aria-hidden="true">{icon}</span>}
          {title}
        </header>
      )}
      {children}
    </section>
  );
}
