import { LandingPage } from "@/ui/business/LandingPage";
import { EN_COPY } from "@/ui/business/landing/en";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "WallRay — One photo. One expert verdict. 24 hours.",
  description:
    "Upload the one thing you're worried about and get an instant, free AI read. Request an expert review to confirm it and put a number on it.",
};

export default function LandingRoute() {
  return <LandingPage copy={EN_COPY} />;
}
