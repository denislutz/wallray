import { cn } from "@/services/tech/TailwindS";
import { buttonVariants } from "@/ui/base/buttonVariants";
import type { VariantProps } from "class-variance-authority";
import type { AnchorHTMLAttributes } from "react";

function LinkButton({
  className,
  variant,
  size,
  fill,
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement> & VariantProps<typeof buttonVariants>) {
  return <a className={cn(buttonVariants({ variant, size, fill }), className)} {...props} />;
}

export { LinkButton };
