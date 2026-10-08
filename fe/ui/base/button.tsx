"use client";

import { Button as ButtonPrimitive } from "@base-ui/react/button";
import type { VariantProps } from "class-variance-authority";

import { cn } from "@/services/tech/TailwindS";
import { buttonVariants } from "./buttonVariants";

function Button({
  className,
  variant = "default",
  size = "default",
  fill,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, fill, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
