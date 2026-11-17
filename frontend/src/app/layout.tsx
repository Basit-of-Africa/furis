import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "FURIS", template: "%s · FURIS" },
  description: "Fountain University Research Intelligence System",
  robots: { index: false, follow: false }, // internal staff data
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body>{children}</body>
    </html>
  );
}
