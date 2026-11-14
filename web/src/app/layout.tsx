import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz", "SOFT", "WONK"],
});

export const metadata: Metadata = {
  title: "FIREIA — Inteligencia de incendios de Paraguay",
  description:
    "Plataforma de inteligencia sobre incendios forestales de Paraguay con satélites NASA FIRMS: mapa de focos activos, observaciones MODIS y VIIRS, eventos de co-detección, calidad del dato y análisis territorial. Datos de demostración (fixtures sintéticos) hasta el piloto real.",
  keywords: [
    "Paraguay",
    "incendios",
    "NASA FIRMS",
    "MODIS",
    "VIIRS",
    "fuegos",
    "hotspots",
    "Space Apps 2026",
    "FIREIA",
  ],
  icons: {
    icon: "/fireia.svg",
  },
  openGraph: {
    title: "FIREIA — Inteligencia de incendios de Paraguay",
    description:
      "Focos activos MODIS × VIIRS sobre Paraguay, con honestidad sobre cada dato · NASA Space Apps 2026",
    siteName: "FIREIA",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} antialiased bg-background text-foreground`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
