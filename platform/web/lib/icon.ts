/** Manifest icons are an emoji or a file path; files aren't served yet, so fall back. */
export function iconText(icon: string): string {
  return icon.length <= 8 && !/[/.]/.test(icon) ? icon : "🤖";
}
