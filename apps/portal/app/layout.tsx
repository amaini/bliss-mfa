import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bliss Secure MFA",
  description: "Managed multi-factor authentication by Bliss IT Solutions",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
