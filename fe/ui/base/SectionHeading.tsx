import { Text } from "@/ui/base/Text";
import type { ReactNode } from "react";

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <Text as="h2" size="3xl" weight="bold" tracking="tight">
      {children}
    </Text>
  );
}

export { SectionHeading };
