import StartTimeS from "@/services/tech/StartTimeS";

export async function GET() {
  return Response.json({ status: "ok", version: StartTimeS.time });
}
