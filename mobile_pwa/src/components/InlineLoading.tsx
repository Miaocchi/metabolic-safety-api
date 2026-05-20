import { Loader2 } from "lucide-react";

export function InlineLoading({ label }: { label: string }) {
  return (
    <div className="inline-loading">
      <Loader2 className="spin" size={17} />
      <span>{label}</span>
    </div>
  );
}
