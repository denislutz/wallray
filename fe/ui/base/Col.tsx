import { cn } from "@/services/tech/TailwindS";
import { type VariantProps, cva } from "class-variance-authority";

const colVariants = cva("flex flex-col", {
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
      stretch: "items-stretch",
    },
    justify: {
      start: "justify-start",
      center: "justify-center",
      end: "justify-end",
      between: "justify-between",
    },
    divided: {
      true: "divide-y divide-border",
    },
    grow: {
      true: "flex-1 min-w-0",
    },
    fill: {
      true: "flex-1",
    },
    py: {
      xs: "py-1",
      sm: "py-2",
      md: "py-4",
      lg: "py-8",
      xl: "py-16",
    },
    px: {
      sm: "px-2",
      md: "px-4",
      lg: "px-8",
    },
    textAlign: {
      center: "text-center",
      left: "text-left",
      right: "text-right",
    },
  },
  defaultVariants: {
    gap: "md",
    align: "stretch",
  },
});

type ColTag = "div" | "main" | "section" | "article" | "aside" | "nav" | "ul" | "ol" | "li";

function Col({
  as: Tag = "div",
  className,
  gap,
  align,
  justify,
  divided,
  grow,
  fill,
  py,
  px,
  textAlign,
  ...props
}: { as?: ColTag } & VariantProps<typeof colVariants> & React.HTMLAttributes<HTMLElement>) {
  return (
    <Tag
      data-slot="col"
      className={cn(
        colVariants({ gap, align, justify, divided, grow, fill, py, px, textAlign }),
        className
      )}
      {...props}
    />
  );
}

export { Col };
