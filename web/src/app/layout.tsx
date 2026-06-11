import type { Metadata } from "next";
import "./globals.css";

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
      <body>{children}</body>
    </html>
  );
}
