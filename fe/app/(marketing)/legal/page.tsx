import { LegalPage } from "@/ui/business/LegalPage";
import { EN_LEGAL } from "@/ui/business/legal/en";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy & Disclaimer — WallRay",
  description: "WallRay's privacy policy and AI report disclaimer.",
};

export default function LegalRoute() {
  return <LegalPage copy={EN_LEGAL} />;
}
