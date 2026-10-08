import { cn } from "@/services/tech/TailwindS";
import type { InputHTMLAttributes } from "react";

const inputCls =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50";

function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input data-slot="input" className={cn(inputCls, className)} {...props} />;
}

export { Input };
