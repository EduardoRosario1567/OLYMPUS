import type { Metadata } from "next";
import { Suspense } from "react";
import { ThemeController } from "@/components/theme-controller";
import { TechnicalShareTools } from "@/components/technical-share-tools";
import "./globals.css";

export const metadata: Metadata = {
  title: "Olympus",
  description: "Transforme uma ideia em software pronto e verificado.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const themeBoot = `(function(){var h=new Date().getHours();var t=h>=6&&h<18?'light':'dark';var e=document.documentElement;e.dataset.theme=t;e.classList.add(t);})();`;
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeBoot }} /></head>
      <body className="app-body min-h-screen antialiased"><ThemeController /><TechnicalShareTools /><Suspense fallback={<p role="status" className="p-6 text-sm text-zinc-500">Carregando Olympus…</p>}>{children}</Suspense></body>
    </html>
  );
}
