import { cn } from "@/services/tech/TailwindS";
import { type VariantProps, cva } from "class-variance-authority";
import type { HTMLAttributes } from "react";

const textVariants = cva("", {
  variants: {
    size: {
      xs: "text-xs",
      sm: "text-sm",
      base: "text-base",
      lg: "text-lg",
      xl: "text-xl",
      "2xl": "text-2xl",
      "3xl": "text-2xl sm:text-3xl",
      display: "text-3xl sm:text-5xl",
    },
    weight: {
      normal: "font-normal",
      medium: "font-medium",
      semibold: "font-semibold",
      bold: "font-bold",
    },
    color: {
      default: "text-foreground",
      muted: "text-muted-foreground",
      destructive: "text-destructive",
      primary: "text-primary",
      accent: "text-accent",
    },
    tracking: {
      tight: "tracking-tight",
      normal: "tracking-normal",
      wide: "tracking-wide",
    },
    mono: {
      true: "tabular-nums font-mono",
    },
    truncate: {
      true: "truncate",
    },
  },
  defaultVariants: {
    size: "sm",
    weight: "normal",
    color: "default",
  },
});

type TextTag = "span" | "p" | "div" | "h1" | "h2" | "h3" | "h4" | "label";

function Text({
  as: Tag = "span",
  size,
  weight,
  color,
  tracking,
  mono,
  truncate,
  className,
  ...props
}: { as?: TextTag } & VariantProps<typeof textVariants> & HTMLAttributes<HTMLElement>) {
  return (
    <Tag
      data-slot="text"
      className={cn(textVariants({ size, weight, color, tracking, mono, truncate }), className)}
      {...props}
    />
  );
}

export { Text };
