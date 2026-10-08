import { LegalPage } from "@/ui/business/LegalPage";
import { EL_LEGAL } from "@/ui/business/legal/el";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Πολιτική Απορρήτου & Αποποίηση Ευθύνης — WallRay",
  description: "Η πολιτική απορρήτου του WallRay και η αποποίηση ευθύνης για τις αναφορές ΤΝ.",
};

export default function LegalElRoute() {
  return <LegalPage copy={EL_LEGAL} />;
}
