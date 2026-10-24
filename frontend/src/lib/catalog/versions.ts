/**
 * Optimistic locking with the API: every answer about a product carries its version
 * (also as ETag); changes send it back in If-Match. A product changed in the meantime
 * answers 412 `precondition_failed`, and the editor offers to load the new state.
 */
export function ifMatch(version: number): { headers: { "If-Match": string } } {
  return { headers: { "If-Match": `"${version}"` } };
}
