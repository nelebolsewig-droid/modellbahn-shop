import { isApiProblem } from "@/lib/api/problem";

/** SumUp's own words if the error is its refusal of a refund, else null. */
export function refusalOf(error: unknown): string | null {
  return isApiProblem(error) && error.code === "refund_rejected"
    ? error.detail
    : null;
}

/** What SumUp answered, shown under the German message so the staff can look it up. */
export function RefundRefusal({ reason }: { reason: string }) {
  return (
    <p className="mt-2 text-hint text-ink-secondary">
      SumUp sagt: <span className="font-mono break-words">{reason}</span>
    </p>
  );
}
