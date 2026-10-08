// ============================================================================
// Types
// ============================================================================

export type DotVariant = "idle" | "ok" | "warning" | "error";

export interface StatusDotProps {
  variant: DotVariant;
  label: string;
  showLabel?: boolean;
}

// ============================================================================
// Private
// ============================================================================

const dotClass: Record<DotVariant, string> = {
  idle: "bg-muted-foreground/40 animate-pulse",
  ok: "bg-success",
  warning: "bg-warning",
  error: "bg-destructive",
};

// ============================================================================
// Component
// ============================================================================

const StatusDot = ({ variant, label, showLabel = true }: StatusDotProps) => (
  <div className="flex items-center gap-2 text-sm text-muted-foreground" title={label}>
    <span className={`inline-block h-2 w-2 rounded-full ${dotClass[variant]}`} />
    {showLabel ? label : <span className="sr-only">{label}</span>}
  </div>
);

export { StatusDot };
