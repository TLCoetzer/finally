// Unique-id helper for client-side React keys (e.g. chat lines).
//
// crypto.randomUUID() only exists in a secure context (HTTPS or localhost).
// FinAlly is served over plain HTTP on port 8000 (PLAN.md §3), so reaching it
// via any non-localhost host (a Docker service name, a LAN IP) makes
// crypto.randomUUID undefined and throws. These ids are only React keys, not
// security-sensitive, so fall back to a non-crypto unique string.
let counter = 0;

export function uid(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  counter += 1;
  return `id-${Date.now().toString(36)}-${counter.toString(36)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}
