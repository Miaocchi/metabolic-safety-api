import type { ReactNode } from "react";

export function Grouped({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grouped">
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}
