// ============================================================================
// Private
// ============================================================================

// Evaluated once when this module is first imported by the running server
// process (i.e. real container start) — mirrors the backend's `/health`
// version field. Must stay out of any statically-prerendered path so it
// reflects process start, not build time; see fe/app/api/health/route.ts.
const time = new Date().toISOString();

// ============================================================================
// Public service API
// ============================================================================

const StartTimeS = { time };
export default StartTimeS;
