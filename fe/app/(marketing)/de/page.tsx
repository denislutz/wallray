import { LandingPage } from "@/ui/business/LandingPage";
import { DE_COPY } from "@/ui/business/landing/de";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "WallRay — Ein Foto. Ein Experturteil. 24 Stunden.",
  description:
    "Laden Sie das eine hoch, das Ihnen Sorgen macht, und erhalten Sie sofort eine kostenlose KI-Einschätzung. Fordern Sie ein Experten-Review an, um sie zu bestätigen und einen Betrag zu nennen.",
};

export default function LandingDeRoute() {
  return <LandingPage copy={DE_COPY} />;
}
