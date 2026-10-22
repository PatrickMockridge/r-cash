export default function Disabled({ title, reason }: { title: string; reason: string }) {
  return (
    <section className="panel">
      <div className="badge">not in v0.1</div>
      <h2>{title}</h2>
      <p className="muted">{reason}</p>
      <p className="muted small">
        The v0.1 specification is explicit about what exists. This screen does not simulate
        a feature the contracts cannot perform.
      </p>
    </section>
  );
}
