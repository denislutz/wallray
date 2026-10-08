import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import AuthS from "@/services/tech/AuthS";
import EnvS from "@/services/tech/EnvS";
import RoutingS from "@/services/tech/RoutingS";

export const proxy = AuthS.auth((req: NextRequest & { auth: unknown }) => {
  const { pathname } = req.nextUrl;
  // NextAuth's auth() wrapper rewrites req.nextUrl's origin to AUTH_URL when trustHost is
  // unset, so req.nextUrl.hostname is always the app host regardless of the real request.
  // Read the raw Host header instead to detect which domain actually served the request.
  const hostname = (req.headers.get("host") ?? "").split(":")[0];

  const appHost = new URL(EnvS.feBaseUrl()).hostname;
  const marketingHost = new URL(EnvS.marketingBaseUrl()).hostname;

  const response = ((): NextResponse => {
    if (RoutingS.isMarketingPath(pathname)) {
      if (hostname !== marketingHost) {
        return NextResponse.redirect(new URL(pathname, EnvS.marketingBaseUrl()));
      }
    } else if (hostname !== appHost) {
      return NextResponse.redirect(new URL(pathname, EnvS.feBaseUrl()));
    }

    const isAuthed = Boolean((req as { auth?: unknown }).auth);

    if (!isAuthed && !RoutingS.isPublicPath(pathname)) {
      return NextResponse.redirect(new URL(RoutingS.paths.signIn(), req.url));
    }

    if (isAuthed && pathname.startsWith(RoutingS.paths.signIn())) {
      return NextResponse.redirect(new URL(RoutingS.paths.reports(), req.url));
    }

    return NextResponse.next();
  })();

  // test.* has no robots.txt/meta-robots handling of its own — without this, it's a real
  // domain with valid SSL and no signal telling crawlers to stay out, so it's indexable exactly
  // like prod the moment Google finds it. This header alone is the fix while test.* is still
  // publicly reachable (Basic Auth — docs/tech/DEVOPS.md — blocks crawl access entirely once
  // live, but until then this is the only thing stopping indexing).
  if (hostname.startsWith("test.")) {
    response.headers.set("X-Robots-Tag", "noindex, nofollow");
  }

  return response;
});

export const config = {
  // Static files under public/ (e.g. /landing/*.jpg) must bypass auth/host
  // redirects entirely — matching them here previously sent image requests
  // through the sign-in redirect instead of serving the file.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
