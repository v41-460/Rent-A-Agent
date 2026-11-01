const TONES = {
  calm: "border-line bg-card text-ink",
  attention: "border-attention bg-attention-bg text-ink",
};

export function Notice({ tone = "calm", children }: { tone?: keyof typeof TONES; children: React.ReactNode }) {
  return (
    <div role="status" className={`rounded-xl border-2 px-5 py-4 text-lg ${TONES[tone]}`}>
      {children}
    </div>
  );
}
