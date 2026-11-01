"use client";

// Draws the blocks an agent's /run returns, in the marketplace's one consistent style.
// The block types come from the shared agent interface (shared/agent_interface).
import { useState } from "react";
import type { Action, Block, FormBlock } from "@shared/agent-interface";
import { Notice } from "./Notice";

type Send = (input: Record<string, unknown>) => void;

const BUTTON = { primary: "btn-primary", secondary: "btn-secondary", danger: "btn-danger" };

function ActionButton({ action, onSend, busy }: { action: Action; onSend: Send; busy: boolean }) {
  return (
    <button
      type="button"
      className={`btn ${BUTTON[action.style ?? "primary"]}`}
      disabled={busy}
      onClick={() => {
        if (action.confirm && !window.confirm(action.confirm)) return;
        onSend(action.input ?? {});
      }}
    >
      {action.label}
    </button>
  );
}

function Form({ block, onSend, busy }: { block: FormBlock; onSend: Send; busy: boolean }) {
  const [values, setValues] = useState<Record<string, string>>({});
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSend(values);
      }}
    >
      {block.fields.map((f) => {
        const id = `field-${f.name}`;
        const common = {
          id,
          name: f.name,
          required: f.required ?? true,
          className: "field",
          value: values[f.name] ?? "",
          onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
            setValues((v) => ({ ...v, [f.name]: e.target.value })),
        };
        return (
          <div key={f.name} className="space-y-1">
            <label htmlFor={id} className="block font-semibold">
              {f.label}
            </label>
            {f.kind === "textarea" ? (
              <textarea rows={5} {...common} />
            ) : (
              <input type={f.kind ?? "text"} {...common} />
            )}
            {f.help ? <p className="text-base text-muted">{f.help}</p> : null}
          </div>
        );
      })}
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {block.submit_label ?? "Continue"}
      </button>
    </form>
  );
}

function OneBlock({ block, onSend, busy }: { block: Block; onSend: Send; busy: boolean }) {
  switch (block.type) {
    case "heading":
      return <h2 className="text-2xl font-bold">{block.text}</h2>;
    case "text":
      return <p className="whitespace-pre-line text-lg">{block.text}</p>;
    case "notice":
      return <Notice level={block.level ?? "info"}>{block.text}</Notice>;
    case "items":
      if (block.items.length === 0) {
        return <p className="text-lg text-muted">{block.empty_text ?? "Nothing to show yet."}</p>;
      }
      return (
        <ul className="divide-y-2 divide-line rounded-xl border-2 border-line bg-card">
          {block.items.map((it, i) => (
            <li key={i} className="flex flex-wrap items-baseline justify-between gap-2 px-5 py-4">
              <div>
                <p className="text-lg font-semibold">{it.title}</p>
                {it.subtitle ? <p className="text-base text-muted">{it.subtitle}</p> : null}
              </div>
              {it.value ? <p className="text-lg font-semibold">{it.value}</p> : null}
            </li>
          ))}
        </ul>
      );
    case "table":
      return (
        <div className="overflow-x-auto rounded-xl border-2 border-line bg-card">
          <table className="w-full text-left text-lg">
            <thead>
              <tr>
                {block.columns.map((c) => (
                  <th key={c} className="border-b-2 border-line px-4 py-3">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className="border-b border-line px-4 py-3">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "link":
      return (
        <a href={block.url} target="_blank" rel="noopener noreferrer" className="text-lg font-semibold text-action underline">
          {block.label}
        </a>
      );
    case "actions":
      return (
        <div className="flex flex-wrap gap-3">
          {block.actions.map((a, i) => (
            <ActionButton key={i} action={a} onSend={onSend} busy={busy} />
          ))}
        </div>
      );
    case "form":
      return <Form block={block} onSend={onSend} busy={busy} />;
    default:
      return null; // Unknown types are rejected by the backend; never render guesses.
  }
}

export function Blocks({
  blocks,
  onSend,
  busy = false,
}: {
  blocks: Block[];
  onSend: Send;
  busy?: boolean;
}) {
  return (
    <div className="space-y-6">
      {blocks.map((b, i) => (
        <OneBlock key={i} block={b} onSend={onSend} busy={busy} />
      ))}
    </div>
  );
}
