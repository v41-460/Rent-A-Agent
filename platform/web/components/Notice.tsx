const TONES = {
  info: "border-line bg-card",
  success: "border-calm bg-calm-bg",
  warning: "border-soon bg-soon-bg",
  danger: "border-attention bg-attention-bg",
};

export function Notice({
  level = "info",
  children,
}: {
  level?: keyof typeof TONES;
  children: React.ReactNode;
}) {
  return (
    <div
      role={level === "danger" ? "alert" : "status"}
      className={`rounded-xl border-2 px-5 py-4 text-lg text-ink ${TONES[level]}`}
    >
      {children}
    </div>
  );
}
