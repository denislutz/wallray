import { LandingPage } from "@/ui/business/LandingPage";
import { EL_COPY } from "@/ui/business/landing/el";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "WallRay — Μία φωτογραφία. Μία ειδική κρίση. 24 ώρες.",
  description:
    "Ανεβάστε αυτό που σας ανησυχεί και λάβετε μια άμεση, δωρεάν αξιολόγηση από ΤΝ. Ζητήστε έλεγχο από ειδικό για να την επιβεβαιώσει και να δώσει ένα ποσό.",
};

export default function LandingElRoute() {
  return <LandingPage copy={EL_COPY} />;
}
