import type { Metadata } from "next";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { rootCssVars } from "@/lib/tokens";
import { Providers } from "./providers";
import { ToastViewport } from "@/components/ui/Toast";

const display = Fraunces({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-display" });
const sans = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["500"], variable: "--font-mono" });

export const metadata: Metadata = { title: "Docintel — Document Intelligence", description: "Document intelligence workspace" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable} ${mono.variable}`}>
      <head><style dangerouslySetInnerHTML={{ __html: rootCssVars }} /></head>
      <body className="font-sans antialiased">
        <Providers>
          {children}
          <ToastViewport />
        </Providers>
      </body>
    </html>
  );
}
