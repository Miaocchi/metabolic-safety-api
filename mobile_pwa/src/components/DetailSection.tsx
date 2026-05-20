import type { ReactNode } from "react";

export function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}
