"use client"

import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useCallback, useEffect, useState } from "react"

import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { api, type Asset } from "@/lib/api"

import { AmbientStage } from "./studio/ambient-stage"
import { CreateView } from "./studio/create-view"
import { GlassNavigation } from "./studio/glass-navigation"
import { LibraryView } from "./studio/library-view"
import { ProductionsView } from "./studio/productions-view"
import { SettingsView } from "./studio/settings-view"
import type { StudioView } from "./studio/types"

export function Studio() {
  const reducedMotion = useReducedMotion()
  const [view, setView] = useState<StudioView>("create")
  const [assets, setAssets] = useState<Asset[]>([])
  const [online, setOnline] = useState(false)

  const refreshAssets = useCallback(async () => {
    const data = await api<{ items: Asset[] }>("/api/assets")
    setAssets(data.items)
  }, [])

  useEffect(() => {
    void api("/api/health").then(() => setOnline(true)).catch(() => setOnline(false))
    void api<{ items: Asset[] }>("/api/assets").then((data) => setAssets(data.items)).catch(() => undefined)
  }, [refreshAssets])

  const changeView = (next: StudioView) => {
    setView(next)
    window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" })
  }

  return (
    <TooltipProvider delayDuration={250}>
      <div className="studio-shell">
        <AmbientStage />
        <GlassNavigation view={view} onViewChange={changeView} online={online} />
        <main className="studio-main">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={view} className="view-frame" exit={reducedMotion ? undefined : { opacity: 0, y: -8 }} transition={{ duration: 0.18 }}>
              {view === "create" ? (
                <CreateView assets={assets} />
              ) : view === "productions" ? (
                <ProductionsView />
              ) : view === "library" ? (
                <LibraryView assets={assets} refreshAssets={refreshAssets} />
              ) : (
                <SettingsView />
              )}
            </motion.div>
          </AnimatePresence>
        </main>
        <Toaster theme="light" richColors position="bottom-right" />
      </div>
    </TooltipProvider>
  )
}
