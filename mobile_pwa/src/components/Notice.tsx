export function Notice({ tone, title, body }: { tone: "warning" | "danger" | "soft"; title: string; body: string }) {
  return (
    <div className={`notice ${tone}`}>
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}
