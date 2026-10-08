import { cn } from "@/services/tech/TailwindS";
import ReactMarkdown, { type Components } from "react-markdown";

// ============================================================================
// Private
// ============================================================================

// No @tailwindcss/typography plugin in this project — element styles are
// mapped by hand to the same size/color tokens `Text` uses, so markdown
// content reads consistently with the rest of the design system.
// Rendered one DOM heading level below markdown's own `##`/`###` — content using this component
// always sits inside a page/section heading already, so a markdown `h2` is semantically an `h3`.
const components: Components = {
  h2: ({ children }) => (
    <h3 className="text-lg font-semibold tracking-tight text-foreground mt-2">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="text-base font-semibold text-foreground mt-1">{children}</h4>
  ),
  p: ({ children }) => <p className="text-sm text-foreground leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => (
    <ul className="text-sm text-foreground leading-relaxed list-disc pl-5 space-y-1">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="text-sm text-foreground leading-relaxed list-decimal pl-5 space-y-1">
      {children}
    </ol>
  ),
  li: ({ children }) => <li>{children}</li>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline">
      {children}
    </a>
  ),
};

// ============================================================================
// Public
// ============================================================================

function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)} data-slot="markdown">
      <ReactMarkdown components={components}>{children}</ReactMarkdown>
    </div>
  );
}

export { Markdown };
