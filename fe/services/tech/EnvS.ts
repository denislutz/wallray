// ============================================================================
// Public service API
// ============================================================================

const apiUrl = (): string => {
  const url = process.env.NEXT_PUBLIC_BE_BASE_URL;
  if (!url) throw new Error("NEXT_PUBLIC_BE_BASE_URL is not set");
  return url;
};

const feBaseUrl = (): string => {
  const url = process.env.NEXT_PUBLIC_FE_BASE_URL;
  if (!url) throw new Error("NEXT_PUBLIC_FE_BASE_URL is not set");
  return url;
};

const marketingBaseUrl = (): string => {
  const url = process.env.NEXT_PUBLIC_MARKETING_BASE_URL;
  if (!url) throw new Error("NEXT_PUBLIC_MARKETING_BASE_URL is not set");
  return url;
};

const devAuth = (): boolean => process.env.NEXT_PUBLIC_DEV_AUTH === "true";

const photoMinCount = (): number => Number(process.env.NEXT_PUBLIC_PHOTO_MIN_COUNT ?? "1");

const photoMaxCount = (): number => Number(process.env.NEXT_PUBLIC_PHOTO_MAX_COUNT ?? "5");

const photoMaxSizeMb = (): number => Number(process.env.NEXT_PUBLIC_PHOTO_MAX_SIZE_MB ?? "10");

const expertReviewPriceEur = (): number =>
  Number(process.env.NEXT_PUBLIC_EXPERT_REVIEW_PRICE_EUR ?? "49.00");

// Falls back to Cloudflare's public "always passes" dummy test site key — safe to ship as a
// default since it's a published testing credential, not a secret. Local dev and CI builds work
// out of the box; a real key (registered for the prod domain in the Cloudflare dashboard) only
// needs to be set via NEXT_PUBLIC_TURNSTILE_SITE_KEY in the prod environment.
const turnstileSiteKey = (): string =>
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || "1x00000000000000000000AA";

const EnvS = {
  apiUrl,
  feBaseUrl,
  marketingBaseUrl,
  devAuth,
  photoMinCount,
  photoMaxCount,
  photoMaxSizeMb,
  expertReviewPriceEur,
  turnstileSiteKey,
};
export default EnvS;
