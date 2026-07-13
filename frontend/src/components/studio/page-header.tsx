import { Sparkles } from "lucide-react"
import type { ReactNode } from "react"

type PageHeaderProps = {
  eyebrow: string
  title: string
  accent: string
  description: string
  action?: ReactNode
}

export function PageHeader({ eyebrow, title, accent, description, action }: PageHeaderProps) {
  const [accentLead, ...accentTail] = accent.trim().split(/\s+/)

  return (
    <header className="page-header">
      <div className="page-heading-copy">
        <div className="eyebrow"><Sparkles aria-hidden="true" /> {eyebrow}</div>
        <h1>
          {title}{" "}
          <em>
            <span className="accent-alternate">{accentLead}</span>
            {accentTail.length > 0 && <span className="accent-rest"> {accentTail.join(" ")}</span>}
          </em>
        </h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  )
}
