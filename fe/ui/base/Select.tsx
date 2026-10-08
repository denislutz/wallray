import { cn } from "@/services/tech/TailwindS";
import { type VariantProps, cva } from "class-variance-authority";
import type { SelectHTMLAttributes } from "react";

const selectVariants = cva(
  "border border-border bg-background text-foreground outline-none transition-colors hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      size: {
        default: "h-8 rounded-md px-3 text-sm",
        sm: "h-7 rounded-[min(var(--radius-md),12px)] px-2 text-[0.8rem]",
      },
    },
    defaultVariants: {
      size: "default",
    },
  }
);

function Select({
  className,
  size,
  ...props
}: Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> & VariantProps<typeof selectVariants>) {
  return (
    <select data-slot="select" className={cn(selectVariants({ size, className }))} {...props} />
  );
}

export { Select };
