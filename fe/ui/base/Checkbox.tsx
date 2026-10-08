import { cn } from "@/services/tech/TailwindS";
import type { InputHTMLAttributes } from "react";

const checkboxCls =
  "size-4 shrink-0 rounded border border-input accent-primary disabled:pointer-events-none disabled:opacity-50";

function Checkbox({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input type="checkbox" data-slot="checkbox" className={cn(checkboxCls, className)} {...props} />
  );
}

export { Checkbox };
