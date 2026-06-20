import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "__APP_NAME__",
  description: "Agentic Takım tarafından üretildi",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
