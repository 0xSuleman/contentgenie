"use client"

import {
  ArrowDownToLine,
  Check,
  CircleHelp,
  Gauge,
  Link2,
  X,
} from "lucide-react"
import { motion, useReducedMotion } from "motion/react"

import { ContentGenieLogo } from "@/components/brand/content-genie-logo"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import type { GenerationJob } from "@/lib/api"

function formatTime(seconds = 0) {
  const minutes = Math.floor(seconds / 60)
  return minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`
}

export function JobPanel({ job, onCancel }: { job: GenerationJob; onCancel: () => void }) {
  const reducedMotion = useReducedMotion()
  const phases = ["Story & research", "Voice & captions", "Visual direction", "Edit & render", "Quality & export"]
  const active = Math.min(4, Math.floor((job.progress || 0) / 20))

  return (
    <motion.section
      className="job-panel glass-panel"
      initial={reducedMotion ? false : { opacity: 0, y: 22, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 155, damping: 20 }}
      aria-live="polite"
    >
      <div className="job-topline">
        <Badge variant="outline" className="live-badge"><i /> Live production</Badge>
        <span className="mono-meta">{formatTime(job.elapsed_seconds)}</span>
      </div>
      <div className="job-title-row">
        <div>
          <h2>{job.status === "complete" ? "Your Shorts are ready" : job.stage}</h2>
          <p>Short {Math.max(job.current_short, 1)} of {job.quantity}</p>
        </div>
        <strong>{job.progress}%</strong>
      </div>
      <Progress value={job.progress} className="job-progress" />
      <div className="phase-grid">
        {phases.map((phase, index) => {
          const done = index < active || job.status === "complete"
          const current = index === active && !done
          return (
            <div key={phase} className={done ? "phase-done" : current ? "phase-active" : ""}>
              <span>{done ? <Check /> : index + 1}</span>
              <small>{phase}</small>
            </div>
          )
        })}
      </div>
      {job.status === "queued" && job.progress === 0 && (
        <div className="job-loading-state">
          <ContentGenieLogo variant="mark" animated />
          <div className="job-skeleton"><Skeleton /><Skeleton /><Skeleton /></div>
        </div>
      )}
      {job.error && <div className="error-banner"><CircleHelp />{job.error}</div>}
      {job.status === "running" && (
        <Button variant="destructive" className="cancel-job" onClick={onCancel}><X /> Cancel after this step</Button>
      )}
      {!!job.outputs.length && (
        <div className="output-grid">
          {job.outputs.map((output) => (
            <Card className="output-card" key={output.video_url}>
              <video controls playsInline preload="metadata" src={output.video_url} />
              <div className="output-copy">
                <h3>{output.title}</h3>
                <div className="output-meta">
                  <span><Gauge /> {output.quality.score ?? "—"}/100</span>
                  <span><Link2 /> {output.sources} sources</span>
                </div>
                <div className="output-actions">
                  <Button asChild><a href={output.download_url || output.video_url} download={`${output.title}.mp4`}><ArrowDownToLine /> Save video</a></Button>
                  {output.manifest_url && <Button variant="outline" asChild><a href={output.manifest_download_url || output.manifest_url} download={`${output.title} - manifest.json`}>Manifest</a></Button>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </motion.section>
  )
}
