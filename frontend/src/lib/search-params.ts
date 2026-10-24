/** The first value of a search parameter as Next.js passes it to a page. */
export function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}
