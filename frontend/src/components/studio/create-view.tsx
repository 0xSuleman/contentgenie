"use client"

import {
  ArrowRight,
  BookOpenText,
  Check,
  Clock3,
  Film,
  Layers3,
  LoaderCircle,
  Mic2,
  Minus,
  Play,
  Plus,
  ShieldCheck,
  Sparkles,
  WandSparkles,
} from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { ContentGenieLogo } from "@/components/brand/content-genie-logo"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api, type Asset, type GenerationJob } from "@/lib/api"

import { JobPanel } from "./job-panel"
import { PageHeader } from "./page-header"

const FORMATS = [
  { id: "reddit", title: "Storytime", detail: "Narrative tension and payoff", icon: BookOpenText, color: "periwinkle" },
  { id: "history", title: "On this day", detail: "Researched historical moments", icon: Clock3, color: "sage" },
  { id: "science", title: "Science bite", detail: "Clear, surprising facts", icon: Sparkles, color: "apricot" },
  { id: "custom", title: "Custom facts", detail: "You choose the subject", icon: WandSparkles, color: "ink" },
] as const

const TONES = ["Cinematic and curious", "Suspenseful storytime", "Warm and reflective", "Fast and witty", "Clear mini-documentary"]
const AUDIENCES = ["General audience", "Curious adults", "Gen Z", "Parents", "Professionals", "Students"]

const initialForm = {
  quantity: 1,
  content_format: "reddit",
  subject: "",
  creative_brief: "",
  target_duration: 50,
  audience: "General audience",
  tone: "Cinematic and curious",
  creator_angle: "Explain why this matters to viewers today with a clear original takeaway.",
  quality_mode: "production",
  voice_persona: "The Energetic Co-Host",
  use_images: true,
  image_count: 10,
  watermark: "",
  footage_mode: "automatic",
  footage_style: "Mixed",
  footage_intensity: "High",
  allow_youtube_cc: true,
  avoid_recent_footage: true,
  background_video: "",
  music_mode: "automatic",
  background_music: "",
  rights_confirmed: false,
}

type FormState = typeof initialForm

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  const id = `select-${label.toLowerCase().replaceAll(" ", "-")}`
  return (
    <div className="field-stack">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={(next) => next && onChange(next)}>
        <SelectTrigger id={id} className="art-select"><SelectValue /></SelectTrigger>
        <SelectContent>{options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent>
      </Select>
    </div>
  )
}

function SettingSwitch({ checked, onCheckedChange, label, description }: { checked: boolean; onCheckedChange: (checked: boolean) => void; label: string; description?: string }) {
  return (
    <div className="setting-switch">
      <div><Label>{label}</Label>{description && <p>{description}</p>}</div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={label} />
    </div>
  )
}

function AccordionHeading({ icon: Icon, title, subtitle }: { icon: typeof Film; title: string; subtitle: string }) {
  return (
    <span className="accordion-heading">
      <span className="accordion-icon"><Icon /></span>
      <span><strong>{title}</strong><small>{subtitle}</small></span>
    </span>
  )
}

export function CreateView({ assets }: { assets: Asset[] }) {
  const reducedMotion = useReducedMotion()
  const [form, setForm] = useState<FormState>(initialForm)
  const [job, setJob] = useState<GenerationJob | null>(null)
  const [error, setError] = useState("")
  const music = useMemo(() => assets.filter((item) => item.type === "background music"), [assets])
  const videos = useMemo(() => assets.filter((item) => item.type === "background video"), [assets])
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }))

  const jobId = job?.id
  const jobStatus = job?.status
  useEffect(() => {
    if (!jobId || !jobStatus || !["queued", "running"].includes(jobStatus)) return
    const timer = window.setInterval(async () => {
      try {
        const latest = await api<GenerationJob>(`/api/jobs/${jobId}`)
        setJob(latest)
        if (latest.status === "complete") toast.success("Your ContentGenie production is ready.")
        if (latest.status === "failed") toast.error(latest.error || "Production failed.")
      } catch (requestError) {
        setError((requestError as Error).message)
      }
    }, 1200)
    return () => window.clearInterval(timer)
  }, [jobId, jobStatus])

  const start = async () => {
    setError("")
    try {
      const created = await api<GenerationJob>("/api/jobs", { method: "POST", body: JSON.stringify(form) })
      setJob(created)
      toast.success("Production queued", { description: "ContentGenie is preparing the editorial pipeline." })
      window.setTimeout(() => document.querySelector(".job-panel")?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" }), 160)
    } catch (requestError) {
      const message = (requestError as Error).message
      setError(message)
      toast.error("Production could not start", { description: message })
    }
  }

  const selectedFormat = FORMATS.find((item) => item.id === form.content_format) || FORMATS[0]

  return (
    <motion.div
      className="studio-view create-view"
      initial={reducedMotion ? false : "hidden"}
      animate="show"
      variants={{ hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.07 } } }}
    >
      <motion.div variants={{ hidden: { opacity: 0, y: 18 }, show: { opacity: 1, y: 0 } }}>
        <PageHeader
          eyebrow="AI production atelier"
          title="Turn a spark into a"
          accent="scroll-stopping story."
          description="Shape the idea. ContentGenie researches, narrates, sources visuals, edits, and quality-checks the final cut."
        />
      </motion.div>

      <div className="create-layout">
        <motion.div className="creator-form" variants={{ hidden: { opacity: 0, y: 24 }, show: { opacity: 1, y: 0 } }}>
          <Card className="paper-card format-card artistic-card">
            <CardHeader className="section-heading">
              <div><span className="section-number">01</span><CardTitle>Choose the storytelling shape</CardTitle></div>
              <Badge variant="outline">Foundation</Badge>
            </CardHeader>
            <CardContent>
              <div className="format-grid">
                {FORMATS.map(({ id, title, detail, icon: Icon, color }, index) => {
                  const selected = form.content_format === id
                  return (
                    <motion.button
                      key={id}
                      type="button"
                      className={`format-choice format-${color} ${selected ? "format-choice-selected" : ""}`}
                      onClick={() => set("content_format", id)}
                      whileHover={reducedMotion ? undefined : { y: -5, rotate: index % 2 ? 0.35 : -0.35 }}
                      whileTap={reducedMotion ? undefined : { scale: 0.98 }}
                      aria-pressed={selected}
                    >
                      <span className="format-icon"><Icon /></span>
                      <strong>{title}</strong>
                      <small>{detail}</small>
                      {selected && <span className="format-check"><Check /></span>}
                    </motion.button>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          <Card className="paper-card story-card artistic-card">
            <CardHeader className="section-heading">
              <div><span className="section-number">02</span><CardTitle>Direct the story</CardTitle></div>
              <span className="section-note">Give the engine a strong starting point</span>
            </CardHeader>
            <CardContent>
              <div className="field-stack">
                <div className="label-line"><Label htmlFor="creative-brief">Idea or creative brief</Label><span>Optional</span></div>
                <Textarea
                  id="creative-brief"
                  rows={5}
                  value={form.creative_brief}
                  onChange={(event) => set("creative_brief", event.target.value)}
                  placeholder="Describe the premise, tension, specific angle, or takeaway you want…"
                />
              </div>
              <Separator />
              <div className="duration-row">
                <div className="duration-control">
                  <div className="label-line"><Label>Target length</Label><strong>{form.target_duration}<small> sec</small></strong></div>
                  <Slider value={[form.target_duration]} min={20} max={90} step={5} onValueChange={(value) => set("target_duration", value[0])} aria-label="Target length in seconds" />
                  <div className="range-labels"><span>20 sec</span><span>90 sec</span></div>
                </div>
                <div className="quantity-control">
                  <Label>Versions</Label>
                  <div>
                    <Button variant="ghost" size="icon-sm" onClick={() => set("quantity", Math.max(1, form.quantity - 1))} aria-label="Decrease versions"><Minus /></Button>
                    <strong>{form.quantity}</strong>
                    <Button variant="ghost" size="icon-sm" onClick={() => set("quantity", Math.min(5, form.quantity + 1))} aria-label="Increase versions"><Plus /></Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Accordion type="single" collapsible className="creative-accordion">
            <AccordionItem value="creative">
              <AccordionTrigger><AccordionHeading icon={Layers3} title="Creative direction" subtitle={`${form.audience} · ${form.tone}`} /></AccordionTrigger>
              <AccordionContent>
                <div className="accordion-fields two-column-fields">
                  <SelectField label="Audience" value={form.audience} options={AUDIENCES} onChange={(value) => set("audience", value)} />
                  <SelectField label="Tone" value={form.tone} options={TONES} onChange={(value) => set("tone", value)} />
                </div>
                <div className="field-stack">
                  <Label htmlFor="creator-angle">Original point of view</Label>
                  <Textarea id="creator-angle" rows={3} value={form.creator_angle} onChange={(event) => set("creator_angle", event.target.value)} />
                </div>
                <div className="setting-choice-row">
                  <div><Label>Research depth</Label><p>Production adds grounding and a second editorial pass.</p></div>
                  <ToggleGroup type="single" variant="outline" spacing={1} value={form.quality_mode} onValueChange={(value) => value && set("quality_mode", value)}>
                    <ToggleGroupItem value="production">Production</ToggleGroupItem>
                    <ToggleGroupItem value="draft">Draft</ToggleGroupItem>
                  </ToggleGroup>
                </div>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="voice">
              <AccordionTrigger><AccordionHeading icon={Mic2} title="Voice & visual language" subtitle={`${form.voice_persona} · ${form.image_count} visual moments`} /></AccordionTrigger>
              <AccordionContent>
                <SelectField label="Voice personality" value={form.voice_persona} options={["The Energetic Co-Host", "The Game Show Host"]} onChange={(value) => set("voice_persona", value)} />
                <SettingSwitch checked={form.use_images} onCheckedChange={(value) => set("use_images", value)} label="Generated story visuals" description="Add custom visual beats alongside gameplay." />
                {form.use_images && (
                  <div className="setting-choice-row">
                    <div><Label>Visual moments</Label><p>More moments increase generation time.</p></div>
                    <ToggleGroup type="single" variant="outline" spacing={1} value={String(form.image_count)} onValueChange={(value) => value && set("image_count", Number(value))}>
                      {[5, 10, 25].map((count) => <ToggleGroupItem key={count} value={String(count)}>{count}</ToggleGroupItem>)}
                    </ToggleGroup>
                  </div>
                )}
                <div className="field-stack"><Label htmlFor="watermark">Channel watermark <span>Optional</span></Label><Input id="watermark" value={form.watermark} onChange={(event) => set("watermark", event.target.value)} placeholder="Your channel name" /></div>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="media">
              <AccordionTrigger><AccordionHeading icon={Film} title="Footage, music & rights" subtitle={form.footage_mode === "automatic" ? "Automatic licensed gameplay" : "Manual library footage"} /></AccordionTrigger>
              <AccordionContent>
                <div className="setting-choice-row">
                  <div><Label>Background footage</Label><p>Automatic mode finds and assembles reusable licensed clips.</p></div>
                  <ToggleGroup type="single" variant="outline" spacing={1} value={form.footage_mode} onValueChange={(value) => value && set("footage_mode", value)}>
                    <ToggleGroupItem value="automatic">Automatic</ToggleGroupItem>
                    <ToggleGroupItem value="manual">My library</ToggleGroupItem>
                  </ToggleGroup>
                </div>
                {form.footage_mode === "automatic" ? (
                  <>
                    <div className="two-column-fields">
                      <SelectField label="Gameplay style" value={form.footage_style} options={["Mixed", "Parkour", "Racing", "Satisfying", "Action"]} onChange={(value) => set("footage_style", value)} />
                      <SelectField label="Cut pace" value={form.footage_intensity} options={["Balanced", "High", "Extreme"]} onChange={(value) => set("footage_intensity", value)} />
                    </div>
                    <SettingSwitch checked={form.allow_youtube_cc} onCheckedChange={(value) => set("allow_youtube_cc", value)} label="Include verified YouTube CC sources" />
                    <SettingSwitch checked={form.avoid_recent_footage} onCheckedChange={(value) => set("avoid_recent_footage", value)} label="Avoid recently used moments" />
                  </>
                ) : (
                  <div className="field-stack">
                    <Label>Background video</Label>
                    <Select value={form.background_video || undefined} onValueChange={(value) => value && set("background_video", value)}>
                      <SelectTrigger className="art-select"><SelectValue placeholder="Choose an asset" /></SelectTrigger>
                      <SelectContent>{videos.map((item) => <SelectItem value={item.name} key={item.name}>{item.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                )}
                <div className="setting-choice-row">
                  <div><Label>Background music</Label><p>Automatic mode finds CC0 or CC BY music that follows the script&apos;s mood and energy.</p></div>
                  <ToggleGroup type="single" variant="outline" spacing={1} value={form.music_mode} onValueChange={(value) => value && set("music_mode", value)}>
                    <ToggleGroupItem value="automatic">Script match</ToggleGroupItem>
                    <ToggleGroupItem value="manual">My library</ToggleGroupItem>
                  </ToggleGroup>
                </div>
                {form.music_mode === "manual" && (
                  <div className="field-stack">
                    <Label>Library track</Label>
                    <Select value={form.background_music || undefined} onValueChange={(value) => value && set("background_music", value)}>
                      <SelectTrigger className="art-select"><SelectValue placeholder="Choose a track" /></SelectTrigger>
                      <SelectContent>{music.map((item) => <SelectItem value={item.name} key={item.name}>{item.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                )}
                <SettingSwitch checked={form.rights_confirmed} onCheckedChange={(value) => set("rights_confirmed", value)} label="I’ll review credits and commercial rights before publishing" description="Required for a publishable export." />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </motion.div>

        <motion.aside
          className="launch-card glass-panel"
          variants={{ hidden: { opacity: 0, x: 22, rotate: 1.2 }, show: { opacity: 1, x: 0, rotate: 0 } }}
        >
          <div className="launch-art">
            <div className="launch-ring launch-ring-one" />
            <div className="launch-ring launch-ring-two" />
            <ContentGenieLogo variant="mark" size="lg" animated />
          </div>
          <span className="mini-label">Production recipe</span>
          <h2>{selectedFormat.title}</h2>
          <p>{form.target_duration}s · {form.quantity} version{form.quantity > 1 ? "s" : ""} · {form.quality_mode === "production" ? "Full research" : "Fast draft"}</p>
          <Separator />
          <div className="recipe-list">
            <span><Check /> Script & editorial pass</span>
            <span><Check /> Voice & timed captions</span>
            <span><Check /> {form.footage_mode === "automatic" ? "Licensed gameplay montage" : "Library footage"}</span>
            <span><Check /> {form.music_mode === "automatic" ? "Script-matched licensed music" : "Selected library music"}</span>
            <span><Check /> Quality report & manifest</span>
          </div>
          <Separator />
          {error && <div className="launch-error">{error}</div>}
          <Button className="generate-button" onClick={start} disabled={job?.status === "running" || job?.status === "queued"}>
            <span>{job?.status === "running" || job?.status === "queued" ? <LoaderCircle className="spin" /> : <Play fill="currentColor" />}{job?.status === "running" ? "Production running" : `Create ${form.quantity > 1 ? `${form.quantity} Shorts` : "my Short"}`}</span>
            <ArrowRight />
          </Button>
          <small className="review-note"><ShieldCheck /> Human review stays in the loop</small>
        </motion.aside>
      </div>

      {job && <JobPanel job={job} onCancel={() => api(`/api/jobs/${job.id}/cancel`, { method: "POST" }).then(() => setJob({ ...job, stage: "Cancelling after the current step" }))} />}
    </motion.div>
  )
}
