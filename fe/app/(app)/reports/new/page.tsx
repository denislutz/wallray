import { NewReportPage } from "@/ui/business/NewReportPage";
import { Suspense } from "react";

export default function NewReportRoute() {
  return (
    <Suspense fallback={null}>
      <NewReportPage />
    </Suspense>
  );
}
