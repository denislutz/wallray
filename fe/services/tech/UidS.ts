// ============================================================================
// Public service API
// ============================================================================

const randomId = (): string =>
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
    b.toString(16).padStart(2, "0")
  ).join("");

const UidS = { randomId };
export default UidS;
