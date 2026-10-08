import { cn } from "@/services/tech/TailwindS";
import type { TextareaHTMLAttributes } from "react";

const textareaCls =
  "w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50";

function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea data-slot="textarea" className={cn(textareaCls, className)} {...props} />;
}

export { Textarea };
