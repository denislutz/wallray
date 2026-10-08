import { Col } from "@/ui/base/Col";
import { Markdown } from "@/ui/base/Markdown";
import { SectionHeading } from "@/ui/base/SectionHeading";
import type { LegalCopy } from "./legal/types";

export function LegalPage({ copy }: { copy: LegalCopy }) {
  return (
    <Col gap="xl" px="md" py="lg" className="mx-auto max-w-2xl">
      <Col as="section" id="privacy" gap="md">
        <SectionHeading>{copy.privacy.heading}</SectionHeading>
        <Markdown>{copy.privacy.markdown}</Markdown>
      </Col>

      <Col as="section" id="disclaimer" gap="md">
        <SectionHeading>{copy.disclaimer.heading}</SectionHeading>
        <Markdown>{copy.disclaimer.markdown}</Markdown>
      </Col>
    </Col>
  );
}
