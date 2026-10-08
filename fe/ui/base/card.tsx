import { cva } from "class-variance-authority";

import { cn } from "@/services/tech/TailwindS";
import type { ComponentProps } from "react";

const cardWidthVariants = cva("", {
  variants: {
    width: {
      auto: "",
      sm: "w-full max-w-sm",
      md: "w-full max-w-lg",
      lg: "w-full max-w-2xl",
      full: "w-full",
    },
  },
});

function Card({
  className,
  size = "default",
  width,
  tone,
  ...props
}: ComponentProps<"div"> & {
  size?: "default" | "sm";
  width?: "auto" | "sm" | "md" | "lg" | "full";
  tone?: "default" | "muted" | "accent";
}) {
  return (
    <div
      data-slot="card"
      data-size={size}
      className={cn(
        "group/card flex h-full flex-col gap-4 overflow-hidden rounded-xl bg-card py-4 text-sm text-card-foreground ring-1 ring-foreground/10 has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:gap-3 data-[size=sm]:py-3 data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-xl *:[img:last-child]:rounded-b-xl",
        cardWidthVariants({ width }),
        tone === "muted" && "bg-muted/50",
        tone === "accent" && "bg-accent/10 ring-accent/25",
        className
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-start gap-1 rounded-t-xl px-4 group-data-[size=sm]/card:px-3 has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-4 group-data-[size=sm]/card:[.border-b]:pb-3",
        className
      )}
      {...props}
    />
  );
}

function CardTitle({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn(
        "font-heading text-base leading-snug font-medium group-data-[size=sm]/card:text-sm",
        className
      )}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

function CardAction({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className)}
      {...props}
    />
  );
}

function CardContent({ className, grow, ...props }: ComponentProps<"div"> & { grow?: boolean }) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-4 group-data-[size=sm]/card:px-3", grow && "flex-1", className)}
      {...props}
    />
  );
}

function CardFooter({
  className,
  justify = "start",
  ...props
}: ComponentProps<"div"> & { justify?: "start" | "center" | "end" | "between" }) {
  const justifyClass = {
    start: "justify-start",
    center: "justify-center",
    end: "justify-end",
    between: "justify-between",
  }[justify];

  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center rounded-b-xl border-t bg-muted/50 p-4 group-data-[size=sm]/card:p-3",
        justifyClass,
        className
      )}
      {...props}
    />
  );
}

export { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle };
