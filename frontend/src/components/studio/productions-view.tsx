"use client"

import {
  ArrowDownToLine,
  CalendarDays,
  CheckCircle2,
  Clapperboard,
  Clock3,
  Copy,
  ExternalLink,
  FileJson,
  Gauge,
  HardDrive,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { ContentGenieLogo } from "@/components/brand/content-genie-logo"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type Production } from "@/lib/api"

import { PageHeader } from "./page-header"

type ProductionSort = "newest" | "title" | "quality"

function formatDuration(seconds?: number | null) {
  if (!seconds) return "Not measured"
  const rounded = Math.round(seconds)
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`
}

function formatBytes(bytes: number) {
  if (!bytes) return "0 MB"
  return `${(bytes / 1024 / 1024).toFixed(bytes > 100 * 1024 * 1024 ? 0 : 1)} MB`
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "Previous export"
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(date)
}

function formatType(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function ProductionsView() {
  const reducedMotion = useReducedMotion()
  const [productions, setProductions] = useState<Production[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState<ProductionSort>("newest")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const loadProductions = useCallback(async (announce = false) => {
    setLoading(true)
    setError("")
    try {
      const data = await api<{ items: Production[] }>("/api/productions")
      setProductions(data.items)
      setSelectedId((current) => data.items.some((item) => item.id === current) ? current : data.items[0]?.id || "")
      if (announce) toast.success("Production archive refreshed")
    } catch (requestError) {
      const detail = (requestError as Error).message
      setError(detail)
      toast.error("Productions could not be loaded", { description: detail })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const frame = requestAnimationFrame(() => void loadProductions())
    return () => cancelAnimationFrame(frame)
  }, [loadProductions])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    const items = productions.filter((production) => !normalized || `${production.title} ${production.content_type}`.toLowerCase().includes(normalized))
    return [...items].sort((left, right) => {
      if (sort === "title") return left.title.localeCompare(right.title)
      if (sort === "quality") return (right.quality_score ?? -1) - (left.quality_score ?? -1)
      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
    })
  }, [productions, query, sort])

  const selected = filtered.find((production) => production.id === selectedId) || filtered[0] || null
  const approved = productions.filter((production) => production.approved).length
  const totalBytes = productions.reduce((total, production) => total + production.size_bytes, 0)

  const copyTitle = async () => {
    if (!selected) return
    await navigator.clipboard.writeText(selected.title)
    toast.success("Title copied")
  }

  const deleteProduction = async (production: Production) => {
    try {
      const data = await api<{ deleted: string; items: Production[] }>(`/api/productions/${production.id}`, { method: "DELETE" })
      setProductions(data.items)
      setSelectedId(data.items[0]?.id || "")
      toast.success("Production deleted", { description: `“${production.title}” and its backend files were removed.` })
    } catch (requestError) {
      toast.error("Production could not be deleted", { description: (requestError as Error).message })
    }
  }

  return (
    <motion.div className="studio-view productions-view" initial={reducedMotion ? false : { opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
      <PageHeader
        eyebrow="Production archive"
        title="Every finished Short, ready to"
        accent="watch and publish."
        description="Preview your complete catalogue, check quality details, and download every export with its real video title."
        action={<Button size="lg" variant="outline" className="archive-refresh" onClick={() => void loadProductions(true)} disabled={loading}><RefreshCw className={loading ? "spin" : ""} /> Refresh archive</Button>}
      />

      <section className="production-summary" aria-label="Production summary">
        <div><span><Clapperboard /></span><strong>{productions.length}</strong><small>Finished videos</small></div>
        <div><span><CheckCircle2 /></span><strong>{approved}</strong><small>Quality approved</small></div>
        <div><span><HardDrive /></span><strong>{formatBytes(totalBytes)}</strong><small>Archive storage</small></div>
      </section>

      <div className="productions-layout">
        <Card className="paper-card production-browser">
          <CardContent>
            <div className="production-toolbar">
              <div className="production-search"><Search /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by video title" aria-label="Search productions" /></div>
              <Select value={sort} onValueChange={(value) => value && setSort(value as ProductionSort)}>
                <SelectTrigger aria-label="Sort productions"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="newest">Newest first</SelectItem><SelectItem value="title">Title A–Z</SelectItem><SelectItem value="quality">Highest quality</SelectItem></SelectContent>
              </Select>
            </div>

            {loading && <div className="production-skeletons">{[1, 2, 3, 4].map((item) => <Skeleton key={item} />)}</div>}
            {!loading && error && <div className="production-error"><ContentGenieLogo variant="mark" size="lg" /><h2>Archive unavailable</h2><p>{error}</p><Button variant="outline" onClick={() => void loadProductions()}>Try again</Button></div>}
            {!loading && !error && !!filtered.length && (
              <div className="production-list">
                {filtered.map((production, index) => (
                  <motion.button
                    type="button"
                    key={production.id}
                    className={production.id === selected?.id ? "production-row production-row-selected" : "production-row"}
                    onClick={() => setSelectedId(production.id)}
                    initial={reducedMotion ? false : { opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(index * 0.035, 0.2) }}
                    aria-pressed={production.id === selected?.id}
                  >
                    <span className="production-poster"><Clapperboard /><small>9:16</small></span>
                    <span className="production-row-copy">
                      <span className="production-row-badges"><Badge variant="outline">{formatType(production.content_type)}</Badge>{production.approved && <Badge className="production-approved"><CheckCircle2 /> Approved</Badge>}</span>
                      <strong>{production.title}</strong>
                      <small><CalendarDays /> {formatDate(production.created_at)} <i /> <Clock3 /> {formatDuration(production.duration_seconds)}</small>
                    </span>
                    <span className="production-row-score"><strong>{production.quality_score ?? "—"}</strong><small>quality</small></span>
                  </motion.button>
                ))}
              </div>
            )}
            {!loading && !error && !filtered.length && (
              <div className="empty-state"><ContentGenieLogo variant="mark" size="lg" animated /><h3>{productions.length ? "No matching videos" : "No productions yet"}</h3><p>{productions.length ? "Try another title or clear the search." : "Finished exports will automatically appear here."}</p></div>
            )}
          </CardContent>
        </Card>

        <aside className="production-preview-column">
          {selected ? (
            <Card className="paper-card production-preview-card">
              <CardContent>
                <div className="production-preview-heading"><div><span className="mono-meta">Selected production</span><h2>{selected.title}</h2></div>{selected.approved && <CheckCircle2 aria-label="Quality approved" />}</div>
                <div className="production-player"><video key={selected.id} controls playsInline preload="metadata" src={selected.video_url} aria-label={`Preview ${selected.title}`} /></div>
                <div className="production-primary-actions">
                  <Button className="art-primary" asChild><a href={selected.download_url}><ArrowDownToLine /> Download video</a></Button>
                  <Button variant="outline" onClick={copyTitle} aria-label="Copy video title"><Copy /> Copy title</Button>
                </div>
                <div className="production-secondary-actions">
                  <Button variant="ghost" asChild><a href={selected.video_url} target="_blank" rel="noreferrer"><ExternalLink /> Open video</a></Button>
                  {selected.manifest_download_url && <Button variant="ghost" asChild><a href={selected.manifest_download_url}><FileJson /> Manifest</a></Button>}
                  <AlertDialog>
                    <AlertDialogTrigger asChild><Button variant="ghost" className="production-delete"><Trash2 /> Delete</Button></AlertDialogTrigger>
                    <AlertDialogContent className="art-dialog">
                      <div className="dialog-brand-mark"><ContentGenieLogo variant="mark" size="lg" animated /></div>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete this produced video?</AlertDialogTitle>
                        <AlertDialogDescription>“{selected.title}” will be permanently deleted from the backend, including its MP4, manifest, and saved YouTube metadata. This cannot be undone.</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter><AlertDialogCancel>Keep video</AlertDialogCancel><AlertDialogAction variant="destructive" onClick={() => void deleteProduction(selected)}>Delete permanently</AlertDialogAction></AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
                <dl className="production-details">
                  <div><dt>Created</dt><dd>{formatDate(selected.created_at)}</dd></div>
                  <div><dt>Duration</dt><dd>{formatDuration(selected.duration_seconds)}</dd></div>
                  <div><dt>Resolution</dt><dd>{selected.width && selected.height ? `${selected.width} × ${selected.height}` : "Portrait export"}</dd></div>
                  <div><dt>File size</dt><dd>{formatBytes(selected.size_bytes)}</dd></div>
                  <div><dt>Quality</dt><dd>{selected.quality_score ? <><Gauge /> {selected.quality_score}/100</> : "Legacy export"}</dd></div>
                  <div><dt>Sources</dt><dd>{selected.sources || "Original story"}</dd></div>
                </dl>
                {selected.description && <p className="production-description">{selected.description.split("\n")[0]}</p>}
              </CardContent>
            </Card>
          ) : (
            <Card className="paper-card production-preview-empty"><CardContent><ContentGenieLogo variant="mark" size="lg" animated /><h2>Select a production</h2><p>Choose a title to open its portrait preview and export actions.</p></CardContent></Card>
          )}
        </aside>
      </div>
    </motion.div>
  )
}
