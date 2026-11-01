import type { Bill } from "./api";
import { FREQUENCY, longDate, money, shortDate } from "./format";

function amountText(bill: Bill): string {
  const exact = bill.min_amount === bill.max_amount;
  return exact ? money(bill.typical_amount) : `About ${money(bill.typical_amount)}`;
}

function whenText(bill: Bill, asOf: string): string {
  if (bill.status === "stopped") return `Last paid ${shortDate(bill.last_date)}`;
  if (bill.status === "possible") {
    return bill.next_due ? `Might come again around ${shortDate(bill.next_due)}` : "Seen once so far";
  }
  if (bill.next_due_earliest && bill.next_due_latest) {
    return `Expected between ${shortDate(bill.next_due_earliest)} and ${shortDate(bill.next_due_latest)}`;
  }
  if (!bill.next_due) return "";
  if (bill.next_due < asOf) return `Was expected ${shortDate(bill.next_due)}`;
  return `Next expected ${longDate(bill.next_due)}`;
}

export function BillCard({ bill, asOf }: { bill: Bill; asOf: string }) {
  const review = bill.flags.filter((f) => f.severity === "review");
  const info = bill.flags.filter((f) => f.severity === "info");
  return (
    <li className="rounded-xl border border-line bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-2xl font-semibold">{bill.payee}</h3>
        <p className="text-2xl font-semibold tabular-nums">{amountText(bill)}</p>
      </div>
      <p className="mt-1 text-lg">{whenText(bill, asOf)}</p>
      <p className="text-lg text-muted">{FREQUENCY[bill.frequency] ?? ""}</p>

      {review.length > 0 && (
        <ul className="mt-4 space-y-3">
          {review.map((flag) => (
            <li key={flag.kind + flag.message} className="rounded-lg bg-attention-bg p-4 text-lg">
              {flag.message}
            </li>
          ))}
        </ul>
      )}
      {info.length > 0 && (
        <ul className="mt-3 space-y-1 text-base text-muted">
          {info.map((flag) => (
            <li key={flag.kind + flag.message}>{flag.message}</li>
          ))}
        </ul>
      )}

      <details className="mt-4 text-base">
        <summary className="cursor-pointer py-1 font-medium text-action underline underline-offset-4">
          Why do I think this is a bill?
        </summary>
        <ul className="mt-2 list-disc space-y-1 pl-6 text-muted">
          {bill.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </details>
    </li>
  );
}
