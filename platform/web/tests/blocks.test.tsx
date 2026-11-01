import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Block } from "@shared/agent-interface";
import { Blocks } from "@/components/Blocks";

const noop = () => undefined;
const render = (blocks: Block[]) => renderToStaticMarkup(<Blocks blocks={blocks} onSend={noop} />);

describe("Blocks", () => {
  it("draws every block type", () => {
    const html = render([
      { type: "heading", text: "Your bills" },
      { type: "text", text: "Hello" },
      { type: "notice", level: "warning", text: "Careful" },
      { type: "items", items: [{ title: "Netflix", subtitle: "Monthly", value: "$15.49" }], empty_text: "" },
      { type: "table", columns: ["A"], rows: [["1"]] },
      { type: "link", label: "Cancel page", url: "https://example.com/cancel" },
      { type: "actions", actions: [{ label: "Refresh", input: {}, style: "primary", confirm: null }] },
      { type: "form", fields: [{ name: "zip", label: "ZIP code", kind: "text", required: true, help: "" }], submit_label: "Go" },
    ]);
    for (const text of ["Your bills", "Hello", "Careful", "Netflix", "$15.49", "Cancel page", "Refresh", "ZIP code", "Go"]) {
      expect(html).toContain(text);
    }
  });

  it("opens links in a new tab without giving the page access", () => {
    const html = render([{ type: "link", label: "x", url: "https://example.com" }]);
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("shows the empty text for an empty list", () => {
    const html = render([{ type: "items", items: [], empty_text: "No bills found" }]);
    expect(html).toContain("No bills found");
  });

  it("uses alert role for danger notices", () => {
    expect(render([{ type: "notice", level: "danger", text: "x" }])).toContain('role="alert"');
  });

  it("ignores unknown block types instead of guessing", () => {
    const html = render([{ type: "video" } as unknown as Block]);
    expect(html).toBe('<div class="space-y-6"></div>');
  });
});
