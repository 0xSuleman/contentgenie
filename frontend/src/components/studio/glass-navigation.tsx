"use client"

import {
  CircleHelp,
  Clapperboard,
  Library,
  Search,
  Settings2,
  WandSparkles,
} from "lucide-react"
import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useReducedMotion,
  useSpring,
} from "motion/react"
import { useEffect, useState, type MouseEvent } from "react"

import { ContentGenieLogo } from "@/components/brand/content-genie-logo"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command"
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuList,
} from "@/components/ui/navigation-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

import { VIEW_LABELS, type StudioView } from "./types"

const destinations = [
  { id: "create" as const, icon: WandSparkles, hint: "New production" },
  { id: "productions" as const, icon: Clapperboard, hint: "Finished videos and downloads" },
  { id: "library" as const, icon: Library, hint: "Licensed footage and assets" },
  { id: "settings" as const, icon: Settings2, hint: "Creative defaults and services" },
]

type GlassNavigationProps = {
  view: StudioView
  onViewChange: (view: StudioView) => void
  online: boolean
}

export function GlassNavigation({ view, onViewChange, online }: GlassNavigationProps) {
  const [commandOpen, setCommandOpen] = useState(false)
  const [isScrolled, setIsScrolled] = useState(false)
  const reducedMotion = useReducedMotion()
  const pointerX = useMotionValue(50)
  const pointerY = useMotionValue(50)
  const smoothX = useSpring(pointerX, { stiffness: 150, damping: 26, mass: 0.45 })
  const smoothY = useSpring(pointerY, { stiffness: 150, damping: 26, mass: 0.45 })
  const sheen = useMotionTemplate`radial-gradient(360px circle at ${smoothX}% ${smoothY}%, rgba(255,255,255,.82), rgba(255,255,255,.18) 43%, transparent 72%)`

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setCommandOpen((current) => !current)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  useEffect(() => {
    let frame = 0
    const updateScrollState = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => setIsScrolled(window.scrollY > 28))
    }

    updateScrollState()
    window.addEventListener("scroll", updateScrollState, { passive: true })
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("scroll", updateScrollState)
    }
  }, [])

  const handlePointer = (event: MouseEvent<HTMLElement>) => {
    if (reducedMotion) return
    const bounds = event.currentTarget.getBoundingClientRect()
    pointerX.set(((event.clientX - bounds.left) / bounds.width) * 100)
    pointerY.set(((event.clientY - bounds.top) / bounds.height) * 100)
  }

  const choose = (next: StudioView) => {
    onViewChange(next)
    setCommandOpen(false)
  }

  return (
    <>
      <motion.header
        className={cn("glass-nav-shell", isScrolled && "glass-nav-shell-scrolled")}
        data-scrolled={isScrolled ? "true" : "false"}
        initial={reducedMotion ? false : { opacity: 0, y: -28, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 170, damping: 22, delay: 0.08 }}
      >
        <nav
          className="glass-nav"
          aria-label="ContentGenie workspace"
          onMouseMove={handlePointer}
          onMouseLeave={() => { pointerX.set(50); pointerY.set(50) }}
        >
          <motion.span className="glass-refraction" style={{ background: sheen }} aria-hidden="true" />
          <span className="glass-edge" aria-hidden="true" />

          <button className="nav-brand-button" onClick={() => choose("create")} aria-label="Open ContentGenie Create">
            <ContentGenieLogo animated />
          </button>

          <NavigationMenu viewport={false} className="workspace-navigation">
            <NavigationMenuList>
              {destinations.map(({ id, icon: Icon }) => (
                <NavigationMenuItem key={id}>
                  <button
                    className={cn("glass-nav-link", view === id && "glass-nav-link-active")}
                    onClick={() => choose(id)}
                    aria-current={view === id ? "page" : undefined}
                  >
                    {view === id && <motion.span className="active-nav-glass" layoutId="active-nav-glass" transition={{ type: "spring", stiffness: 360, damping: 32 }} />}
                    <Icon aria-hidden="true" />
                    <span>{VIEW_LABELS[id]}</span>
                  </button>
                </NavigationMenuItem>
              ))}
            </NavigationMenuList>
          </NavigationMenu>

          <div className="nav-utilities">
            <Button variant="outline" className="command-launcher" onClick={() => setCommandOpen(true)}>
              <Search aria-hidden="true" />
              <span>Quick find</span>
              <kbd>Ctrl K</kbd>
            </Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="engine-indicator" aria-label={online ? "Production engine online" : "Production engine offline"}><i className={online ? "online" : ""} /></button>
              </TooltipTrigger>
              <TooltipContent side="bottom">{online ? "Python + FFmpeg ready" : "Production engine offline"}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild><Button variant="ghost" size="icon" className="nav-icon-button" aria-label="ContentGenie help"><CircleHelp /></Button></TooltipTrigger>
              <TooltipContent side="bottom">Describe a specific hook, tension, and payoff for stronger results.</TooltipContent>
            </Tooltip>
            <Avatar className="nav-avatar">
              <AvatarFallback>CG</AvatarFallback>
            </Avatar>
          </div>
        </nav>
      </motion.header>

      <CommandDialog
        open={commandOpen}
        onOpenChange={setCommandOpen}
        title="ContentGenie quick find"
        description="Jump to a workspace"
        className="command-glass"
      >
        <div className="command-brand"><ContentGenieLogo size="lg" animated /><span>Jump anywhere in your creative studio.</span></div>
        <CommandInput placeholder="Search Create, Media Library, or Settings…" />
        <CommandList>
          <CommandEmpty>No ContentGenie destination found.</CommandEmpty>
          <CommandGroup heading="Workspace">
            {destinations.map(({ id, icon: Icon, hint }, index) => (
              <CommandItem key={id} value={`${VIEW_LABELS[id]} ${hint}`} onSelect={() => choose(id)}>
                <span className="command-item-icon"><Icon /></span>
                <span><strong>{VIEW_LABELS[id]}</strong><small>{hint}</small></span>
                <CommandShortcut>{index + 1}</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  )
}
