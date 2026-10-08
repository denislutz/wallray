import { cn } from "@/services/tech/TailwindS";
import { type VariantProps, cva } from "class-variance-authority";
import type { HTMLAttributes } from "react";

const rowVariants = cva("flex flex-row", {
  variants: {
    gap: {
      none: "gap-0",
      xs: "gap-1",
      sm: "gap-2",
      md: "gap-4",
      lg: "gap-6",
      xl: "gap-8",
    },
    align: {
      start: "items-start",
      center: "items-center",
      end: "items-end",
      baseline: "items-baseline",
      stretch: "items-stretch",
    },
    justify: {
      start: "justify-start",
      center: "justify-center",
      end: "justify-end",
      between: "justify-between",
      around: "justify-around",
      evenly: "justify-evenly",
    },
    wrap: {
      true: "flex-wrap",
    },
    grow: {
      true: "flex-1 min-w-0",
    },
    py: {
      xs: "py-1",
      sm: "py-2",
      md: "py-4",
    },
    px: {
      sm: "px-2",
      md: "px-4",
      lg: "px-8",
    },
    color: {
      destructive: "text-destructive",
      muted: "text-muted-foreground",
    },
  },
  defaultVariants: {
    gap: "sm",
    align: "center",
    justify: "start",
  },
});

type RowTag = "div" | "header" | "footer" | "nav" | "section" | "ul" | "ol" | "li";

function Row({
  as: Tag = "div",
  className,
  gap,
  align,
  justify,
  wrap,
  grow,
  py,
  px,
  color,
  ...props
}: { as?: RowTag } & VariantProps<typeof rowVariants> & HTMLAttributes<HTMLElement>) {
  return (
    <Tag
      data-slot="row"
      className={cn(rowVariants({ gap, align, justify, wrap, grow, py, px, color }), className)}
      {...props}
    />
  );
}

export { Row };
