export function OverlayNotice({ tone, body }: { tone: "soft" | "warning" | "danger"; body: string }) {
  return (
    <div className={`notice overlay-notice ${tone}`} role="note">
      <span>{body}</span>
    </div>
  );
}
