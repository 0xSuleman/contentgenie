import type { Metadata } from "next"
import { Cinzel_Decorative, Cormorant_Garamond, IBM_Plex_Mono, Italiana, Manrope } from "next/font/google"

import "./globals.css"

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  display: "swap",
})

const cormorant = Cormorant_Garamond({
  variable: "--font-cormorant",
  subsets: ["latin"],
  style: ["normal", "italic"],
  display: "swap",
})

const cinzel = Cinzel_Decorative({
  variable: "--font-cinzel",
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
})

const italiana = Italiana({
  variable: "--font-italiana",
  subsets: ["latin"],
  weight: "400",
  display: "swap",
})

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
})

export const metadata: Metadata = {
  title: "ContentGenie — Artistic short-form production studio",
  description: "Create researched, narrated, visually sourced, production-ready short-form videos.",
  applicationName: "ContentGenie",
  icons: { icon: "/icon.svg" },
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${manrope.variable} ${cormorant.variable} ${cinzel.variable} ${italiana.variable} ${plexMono.variable} h-full antialiased`}>
      <body>{children}</body>
    </html>
  )
}
