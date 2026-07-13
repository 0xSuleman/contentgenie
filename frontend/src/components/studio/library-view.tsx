"use client"

import {
  ArrowDownToLine,
  AudioLines,
  Film,
  Image as ImageIcon,
  Link2,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  Zap,
} from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useMemo, useState } from "react"
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api, type Asset, type FootageCandidate } from "@/lib/api"

import { PageHeader } from "./page-header"

export function LibraryView({ assets, refreshAssets }: { assets: Asset[]; refreshAssets: () => Promise<void> }) {
  const reducedMotion = useReducedMotion()
  const [discoveryQuery, setDiscoveryQuery] = useState("")
  const [filterQuery, setFilterQuery] = useState("")
  const [style, setStyle] = useState("Mixed")
  const [sources, setSources] = useState(["wikimedia", "youtube"])
  const [results, setResults] = useState<FootageCandidate[]>([])
  const [searching, setSearching] = useState(false)
  const [message, setMessage] = useState("")
  const [addOpen, setAddOpen] = useState(false)
  const [assetName, setAssetName] = useState("")
  const [assetType, setAssetType] = useState("background video")
  const [assetUrl, setAssetUrl] = useState("")

  const filtered = useMemo(
    () => assets.filter((asset) => `${asset.name} ${asset.type} ${asset.source}`.toLowerCase().includes(filterQuery.toLowerCase())),
    [assets, filterQuery],
  )

  const discover = async () => {
    setSearching(true)
    setMessage("")
    try {
      const data = await api<{ items: FootageCandidate[]; warnings: string[] }>("/api/footage/discover", {
        method: "POST",
        body: JSON.stringify({ style, sources, query: discoveryQuery }),
      })
      setResults(data.items)
      const nextMessage = data.items.length ? `${data.items.length} rights-checked sources found` : data.warnings.join(" ") || "No eligible sources found."
      setMessage(nextMessage)
      if (data.items.length) toast.success(nextMessage)
    } catch (error) {
      const detail = (error as Error).message
      setMessage(detail)
      toast.error("Discovery failed", { description: detail })
    } finally {
      setSearching(false)
    }
  }

  const acquire = async (candidate: FootageCandidate) => {
    const notification = toast.loading(`Checking “${candidate.title}”…`)
    try {
      await api("/api/footage/acquire", { method: "POST", body: JSON.stringify({ candidate }) })
      await refreshAssets()
      toast.success("Footage added", { id: notification, description: "License evidence and attribution were saved." })
    } catch (error) {
      toast.error("Footage could not be added", { id: notification, description: (error as Error).message })
    }
  }

  const addRemote = async () => {
    const form = new FormData()
    form.set("name", assetName)
    form.set("asset_type", assetType)
    form.set("url", assetUrl)
    try {
      await api("/api/assets/remote", { method: "POST", body: form })
      setAddOpen(false)
      setAssetName("")
      setAssetUrl("")
      await refreshAssets()
      toast.success("Remote asset added")
    } catch (error) {
      toast.error("Asset could not be added", { description: (error as Error).message })
    }
  }

  const remove = async (asset: Asset) => {
    try {
      await api(`/api/assets/${encodeURIComponent(asset.name)}`, { method: "DELETE" })
      await refreshAssets()
      toast.success(`${asset.name} removed`)
    } catch (error) {
      toast.error("Asset could not be removed", { description: (error as Error).message })
    }
  }

  return (
    <motion.div className="studio-view library-view" initial={reducedMotion ? false : { opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
      <PageHeader
        eyebrow="Media intelligence"
        title="Build a visual library with"
        accent="rights you can trace."
        description="Find open gameplay, keep licensing evidence, and reuse your strongest production assets."
        action={<Button size="lg" className="art-primary" onClick={() => setAddOpen(true)}><Plus /> Add asset</Button>}
      />

      <Card className="paper-card discovery-card artistic-card">
        <CardHeader className="discovery-heading">
          <span className="feature-icon"><Search /></span>
          <div><CardTitle>Discover open gameplay</CardTitle><p>Commercial-editing eligibility is checked before anything enters your library.</p></div>
          <Badge className="rights-badge"><ShieldCheck /> Rights gate on</Badge>
        </CardHeader>
        <CardContent>
          <div className="discovery-toolbar">
            <div className="field-stack discovery-search"><Label htmlFor="discovery-query">Search direction</Label><Input id="discovery-query" value={discoveryQuery} onChange={(event) => setDiscoveryQuery(event.target.value)} placeholder="Optional — e.g. parkour speedrun" /></div>
            <div className="field-stack"><Label>Visual style</Label><Select value={style} onValueChange={(value) => value && setStyle(value)}><SelectTrigger className="art-select"><SelectValue /></SelectTrigger><SelectContent>{["Mixed", "Parkour", "Racing", "Satisfying", "Action"].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></div>
            <Button className="discover-button" onClick={discover} disabled={searching || !sources.length}>{searching ? <LoaderCircle className="spin" /> : <Search />} Search sources</Button>
          </div>
          <div className="source-row">
            <Label>Search in</Label>
            <ToggleGroup type="multiple" variant="outline" spacing={1} value={sources} onValueChange={setSources}>
              <ToggleGroupItem value="wikimedia">Wikimedia</ToggleGroupItem>
              <ToggleGroupItem value="youtube">YouTube CC</ToggleGroupItem>
              <ToggleGroupItem value="archive">Internet Archive</ToggleGroupItem>
            </ToggleGroup>
          </div>
          {message && <div className="status-line"><Zap />{message}</div>}
          {searching && <div className="result-skeletons">{[1, 2, 3].map((item) => <Skeleton key={item} />)}</div>}
          {!!results.length && !searching && (
            <motion.div className="discovery-results" initial={reducedMotion ? false : { opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
              {results.slice(0, 8).map((candidate) => (
                <article key={candidate.key}>
                  <div className="result-thumb"><Film /><span>{candidate.resolution}</span></div>
                  <div className="result-copy">
                    <div className="asset-badges"><Badge variant="outline">{candidate.source}</Badge><Badge variant="secondary">{candidate.license_name}</Badge></div>
                    <h3>{candidate.title}</h3>
                    <p>{candidate.creator || "Open media contributor"}</p>
                  </div>
                  <div className="result-score"><strong>{Math.round((candidate.preliminary_score || 0) * 100)}</strong><small>match</small></div>
                  <Button variant="outline" onClick={() => acquire(candidate)}><ArrowDownToLine /> Add</Button>
                </article>
              ))}
            </motion.div>
          )}
        </CardContent>
      </Card>

      <section className="library-section">
        <div className="library-title">
          <div><h2>Your production assets</h2><p>{assets.length} items available to the editor</p></div>
          <div className="asset-filter"><Search /><Input value={filterQuery} onChange={(event) => setFilterQuery(event.target.value)} placeholder="Filter assets" aria-label="Filter production assets" /></div>
        </div>
        <div className="asset-table paper-card">
          <div className="asset-table-head"><span>Asset</span><span>Type</span><span>Source & license</span><span>Action</span></div>
          {filtered.map((asset) => (
            <div className="asset-row" key={asset.name}>
              <div><span className="asset-icon">{asset.type.includes("music") || asset.type === "audio" ? <AudioLines /> : asset.type === "image" ? <ImageIcon /> : <Film />}</span><strong>{asset.name}</strong></div>
              <span>{asset.type}</span>
              <div><strong>{asset.source || "Local"}</strong><small>{asset.license || "User supplied"}</small></div>
              <AlertDialog>
                <AlertDialogTrigger asChild><Button variant="ghost" size="icon" aria-label={`Remove ${asset.name}`}><Trash2 /></Button></AlertDialogTrigger>
                <AlertDialogContent className="art-dialog">
                  <div className="dialog-brand-mark"><ContentGenieLogo variant="mark" size="lg" animated /></div>
                  <AlertDialogHeader><AlertDialogTitle>Remove this production asset?</AlertDialogTitle><AlertDialogDescription>{asset.name} will be removed from ContentGenie’s library. Existing rendered videos will not be changed.</AlertDialogDescription></AlertDialogHeader>
                  <AlertDialogFooter><AlertDialogCancel>Keep asset</AlertDialogCancel><AlertDialogAction onClick={() => remove(asset)}>Remove asset</AlertDialogAction></AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          ))}
          {!filtered.length && (
            <div className="empty-state"><ContentGenieLogo variant="mark" size="lg" animated /><h3>No matching assets</h3><p>Try a different filter or discover new open gameplay above.</p></div>
          )}
        </div>
      </section>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="art-dialog">
          <DialogHeader>
            <div className="dialog-brand-mark"><ContentGenieLogo variant="mark" size="lg" animated /></div>
            <DialogTitle>Add a remote asset</DialogTitle>
            <DialogDescription>Save a licensed YouTube link or another media URL to your production library.</DialogDescription>
          </DialogHeader>
          <Separator />
          <div className="dialog-fields">
            <div className="field-stack"><Label htmlFor="asset-name">Recognizable name</Label><Input id="asset-name" value={assetName} onChange={(event) => setAssetName(event.target.value)} /></div>
            <div className="field-stack"><Label>Asset type</Label><Select value={assetType} onValueChange={(value) => value && setAssetType(value)}><SelectTrigger className="art-select"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="background video">Background video</SelectItem><SelectItem value="background music">Background music</SelectItem></SelectContent></Select></div>
            <div className="field-stack"><Label htmlFor="asset-url">Media URL</Label><Input id="asset-url" value={assetUrl} onChange={(event) => setAssetUrl(event.target.value)} placeholder="https://youtube.com/watch?v=…" /></div>
          </div>
          <Button className="art-primary full-button" onClick={addRemote} disabled={!assetName.trim() || !assetUrl.trim()}><Link2 /> Add to library</Button>
        </DialogContent>
      </Dialog>
    </motion.div>
  )
}
