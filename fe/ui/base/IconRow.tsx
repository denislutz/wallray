import { Row } from "@/ui/base/Row";
import { Text } from "@/ui/base/Text";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

const iconClass: Record<"muted" | "primary" | "accent", string> = {
  muted: "text-muted-foreground",
  primary: "text-primary",
  accent: "text-accent",
};

function IconRow({
  icon: Icon,
  tone = "muted",
  children,
}: {
  icon: LucideIcon;
  tone?: "muted" | "primary" | "accent";
  children: ReactNode;
}) {
  return (
    <Row align="start" gap="sm">
      <Icon aria-hidden="true" className={`mt-0.5 size-4 shrink-0 ${iconClass[tone]}`} />
      <Text size="base" color="muted">
        {children}
      </Text>
    </Row>
  );
}

export { IconRow };
