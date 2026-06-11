import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "@/components/AuthGate";

export const metadata: Metadata = {
  title: "Friday",
  description: "Self-modifying autonomous agent — Cursor-style control plane",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
