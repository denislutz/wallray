import { cn } from "@/services/tech/TailwindS";
import { type VariantProps, cva } from "class-variance-authority";
import type { ComponentProps } from "react";

const gridVariants = cva("grid", {
  variants: {
    cols: {
      "2": "grid-cols-1 sm:grid-cols-2",
      "4": "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
    },
    gap: {
      sm: "gap-2",
      md: "gap-4",
      lg: "gap-6",
    },
  },
  defaultVariants: {
    gap: "md",
  },
});

function Grid({
  className,
  cols,
  gap,
  ...props
}: ComponentProps<"div"> & VariantProps<typeof gridVariants>) {
  return <div data-slot="grid" className={cn(gridVariants({ cols, gap }), className)} {...props} />;
}

export { Grid };
