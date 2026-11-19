import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FairAsk",
  description: "Is the asking price fair? A fair value range, verdict and cost to own for homes in Waterloo Region and the GTA.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // Browser extensions add attributes to <html> before React loads.
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
