// Display formatting only. All arithmetic happens in the backend.

export function money(amount: string): string {
  const [whole, cents = "00"] = amount.split(".");
  return `$${Number(whole).toLocaleString("en-US")}.${cents.padEnd(2, "0")}`;
}

function parse(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function longDate(iso: string): string {
  return parse(iso).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

export function shortDate(iso: string): string {
  return parse(iso).toLocaleDateString("en-US", { month: "long", day: "numeric" });
}

export const FREQUENCY: Record<string, string> = {
  weekly: "Every week",
  biweekly: "Every two weeks",
  monthly: "Every month",
  quarterly: "Every three months",
  semiannual: "Every six months",
  annual: "Once a year",
  irregular: "Every few weeks",
  unknown: "Not sure yet",
};
