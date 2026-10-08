// ============================================================================
// Private
// ============================================================================

const signIn = () => "/auth/signin";
const reports = () => "/reports";

// Restarting a failed report carries its name/description forward via query params — the
// customer shouldn't have to retype what they already wrote.
const newReport = (prefill?: { name?: string | null; description?: string | null }) => {
  if (!prefill) return "/reports/new";
  const params = new URLSearchParams();
  if (prefill.name) params.set("name", prefill.name);
  if (prefill.description) params.set("description", prefill.description);
  const qs = params.toString();
  return qs ? `/reports/new?${qs}` : "/reports/new";
};

const reportDetail = (jobId: string) => `/reports/${jobId}`;
const account = () => "/account";
const expertReviews = () => "/expert/reviews";
const expertReview = (jobId: string) => `/expert/review/${jobId}`;
const legal = () => "/legal";

const PUBLIC_PREFIXES = ["/api/auth", "/auth", "/de", "/ru", "/el"];
const PUBLIC_EXACT_PATHS = ["/", "/api/health", "/legal"];

const MARKETING_PREFIXES = ["/de", "/ru", "/el"];
const MARKETING_EXACT_PATHS = ["/", "/legal"];

// ============================================================================
// Public service API
// ============================================================================

const paths = {
  signIn,
  reports,
  newReport,
  reportDetail,
  account,
  expertReviews,
  expertReview,
  legal,
};

const isPublicPath = (pathname: string): boolean =>
  PUBLIC_EXACT_PATHS.includes(pathname) ||
  PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));

const isMarketingPath = (pathname: string): boolean =>
  MARKETING_EXACT_PATHS.includes(pathname) ||
  MARKETING_PREFIXES.some((prefix) => pathname.startsWith(prefix));

const RoutingS = { paths, isPublicPath, isMarketingPath };
export default RoutingS;
