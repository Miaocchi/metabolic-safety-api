export function EmptyState({
  icon,
  title,
  description,
  action,
  compact,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`empty-state${compact ? " compact" : ""}`}>
      {icon}
      <strong>{title}</strong>
      {description ? <span>{description}</span> : null}
      {action}
    </div>
  );
}
