import type { Metadata } from "next";
import { Header } from "@/components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: "Rent an Agent",
  description: "Friendly AI helpers for everyday tasks.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="bg-ink px-4 py-2 text-center text-base text-white">
          Test version. Payments are pretend, and no real money is ever charged.
        </div>
        <Header />
        <main className="mx-auto max-w-4xl px-4 py-8 sm:py-12">{children}</main>
      </body>
    </html>
  );
}
