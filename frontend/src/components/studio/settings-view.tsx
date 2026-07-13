"use client"

import { AudioLines, Check, Image as ImageIcon, KeyRound, Settings2 } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Slider } from "@/components/ui/slider"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"

import { PageHeader } from "./page-header"

function SettingsCardHeading({ icon: Icon, title, description }: { icon: typeof KeyRound; title: string; description: string }) {
  return (
    <CardHeader className="settings-card-title">
      <span><Icon /></span>
      <div><CardTitle>{title}</CardTitle><p>{description}</p></div>
    </CardHeader>
  )
}

export function SettingsView() {
  const reducedMotion = useReducedMotion()
  const [values, setValues] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api<{ values: Record<string, string> }>("/api/settings")
      .then((data) => setValues(data.values))
      .catch((error) => toast.error("Settings could not be loaded", { description: (error as Error).message }))
      .finally(() => setLoading(false))
  }, [])

  const set = (key: string, value: string) => setValues((current) => ({ ...current, [key]: value }))
  const save = async () => {
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify({ values }) })
      setSaved(true)
      toast.success("Creative defaults saved")
      window.setTimeout(() => setSaved(false), 2200)
    } catch (error) {
      toast.error("Settings could not be saved", { description: (error as Error).message })
    }
  }

  return (
    <motion.div className="studio-view settings-view" initial={reducedMotion ? false : { opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
      <PageHeader
        eyebrow="Studio preferences"
        title="Tune the atelier to"
        accent="your creative fingerprint."
        description="Connect services once, then define the visual, caption, and sound defaults behind every export."
        action={<Button size="lg" className="art-primary" onClick={save} disabled={loading}>{saved ? <Check /> : <Settings2 />}{saved ? "Saved" : "Save changes"}</Button>}
      />

      {loading ? (
        <div className="settings-layout settings-loading">{[1, 2, 3].map((item) => <Skeleton key={item} />)}</div>
      ) : (
        <motion.div className="settings-layout" initial={reducedMotion ? false : "hidden"} animate="show" variants={{ hidden: {}, show: { transition: { staggerChildren: 0.1 } } }}>
          <motion.div variants={{ hidden: { opacity: 0, y: 18 }, show: { opacity: 1, y: 0 } }}>
            <Card className="paper-card settings-card artistic-card">
              <SettingsCardHeading icon={KeyRound} title="Connections" description="Stored only in your local ContentGenie database." />
              <CardContent>
                {[
                  ["GEMINI_API_KEY", "Gemini API key", "Scripts, research, and Gemini voice"],
                  ["HUGGINGFACE_TOKEN", "Hugging Face token", "Optional model access"],
                  ["YOUTUBE_API_KEY", "YouTube Data API key", "Faster Creative Commons discovery"],
                ].map(([key, label, hint], index) => (
                  <div key={key}>
                    {index > 0 && <Separator />}
                    <div className="field-stack secret-field">
                      <div className="label-line"><Label htmlFor={key}>{label}</Label><span>{hint}</span></div>
                      <Input id={key} type="password" value={values[key] || ""} onChange={(event) => set(key, event.target.value)} placeholder="Not configured" autoComplete="off" />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={{ hidden: { opacity: 0, y: 18 }, show: { opacity: 1, y: 0 } }}>
            <Card className="paper-card settings-card artistic-card">
              <SettingsCardHeading icon={ImageIcon} title="Visual defaults" description="A consistent image language for every Short." />
              <CardContent>
                <div className="field-stack"><Label>Image model</Label><Select value={values.IMAGE_PROVIDER || "zimage_local"} onValueChange={(value) => value && set("IMAGE_PROVIDER", value)}><SelectTrigger className="art-select"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="zimage_local">Z-Image local</SelectItem></SelectContent></Select></div>
                <div className="field-stack"><Label htmlFor="visual-style">Visual style prompt</Label><Textarea id="visual-style" rows={7} value={values.SHORT_VISUAL_STYLE_PROMPT || ""} onChange={(event) => set("SHORT_VISUAL_STYLE_PROMPT", event.target.value)} placeholder="Cinematic, realistic, emotionally clear…" /></div>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={{ hidden: { opacity: 0, y: 18 }, show: { opacity: 1, y: 0 } }}>
            <Card className="paper-card settings-card settings-card-wide artistic-card">
              <SettingsCardHeading icon={AudioLines} title="Captions & sound" description="Set the default reading and listening experience." />
              <CardContent>
                <div className="two-column-fields">
                  <div className="field-stack"><Label>Caption style</Label><Select value={values.SHORT_CAPTION_STYLE || "Traditional"} onValueChange={(value) => value && set("SHORT_CAPTION_STYLE", value)}><SelectTrigger className="art-select"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="Traditional">Traditional</SelectItem><SelectItem value="Color bounce">Color bounce</SelectItem></SelectContent></Select></div>
                  <div className="field-stack"><Label>Caption position</Label><Select value={values.SHORT_CAPTION_POSITION || "Center"} onValueChange={(value) => value && set("SHORT_CAPTION_POSITION", value)}><SelectTrigger className="art-select"><SelectValue /></SelectTrigger><SelectContent>{["Upper middle", "Center", "Lower third", "Bottom"].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></div>
                </div>
                <Separator />
                <div className="sound-range"><div className="label-line"><Label>Background music</Label><strong>{values.SHORT_BACKGROUND_MUSIC_VOLUME || "0.07"}</strong></div><Slider min={0} max={0.5} step={0.01} value={[Number(values.SHORT_BACKGROUND_MUSIC_VOLUME || "0.07")]} onValueChange={(value) => set("SHORT_BACKGROUND_MUSIC_VOLUME", String(value[0]))} aria-label="Background music volume" /></div>
                <div className="sound-range"><div className="label-line"><Label>Sound effect level</Label><strong>{values.SHORT_SFX_VOLUME || "0.35"}</strong></div><Slider min={0} max={1} step={0.05} value={[Number(values.SHORT_SFX_VOLUME || "0.35")]} onValueChange={(value) => set("SHORT_SFX_VOLUME", String(value[0]))} aria-label="Sound effect volume" /></div>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      )}
    </motion.div>
  )
}
