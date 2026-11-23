import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "NACT | NOC/SOC", description: "Network and Security Operations" };

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
