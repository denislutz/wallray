import { LandingPage } from "@/ui/business/LandingPage";
import { RU_COPY } from "@/ui/business/landing/ru";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "WallRay — Одно фото. Экспертное заключение. 24 часа.",
  description:
    "Загрузите то, что вас беспокоит, и получите мгновенную бесплатную оценку от ИИ. Закажите экспертную проверку, чтобы подтвердить её и назвать сумму.",
};

export default function LandingRuRoute() {
  return <LandingPage copy={RU_COPY} />;
}
