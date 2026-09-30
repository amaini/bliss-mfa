import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bliss Secure MFA",
  description: "Local MFA management portal",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
