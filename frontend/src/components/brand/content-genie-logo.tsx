"use client"

import { motion } from "motion/react"

import { cn } from "@/lib/utils"

type ContentGenieLogoProps = {
  variant?: "mark" | "lockup"
  size?: "sm" | "md" | "lg"
  tone?: "color" | "ink" | "light"
  animated?: boolean
  className?: string
}

const sizes = {
  sm: 28,
  md: 38,
  lg: 54,
}

function LampMark({ size, tone, animated }: Pick<Required<ContentGenieLogoProps>, "size" | "tone" | "animated">) {
  const dimension = sizes[size]
  const ink = tone === "light" ? "#FFFDF8" : "#132238"
  const smoke = tone === "color" ? "#7488C9" : ink
  const spark = tone === "color" ? "#DDA077" : ink

  return (
    <motion.svg
      aria-hidden="true"
      className="genie-mark"
      viewBox="0 0 64 64"
      width={dimension}
      height={dimension}
      fill="none"
      initial={false}
      animate={animated ? { rotate: [0, -1.5, 1, 0] } : undefined}
      transition={animated ? { duration: 7, repeat: Infinity, ease: "easeInOut" } : undefined}
    >
      <path
        className="genie-smoke"
        d="M34.7 26.2c-5.4-3.1-6-7.4-2.6-10.2 2.3-1.9 2.6-4.1.6-6.7 5.8 1.8 8.8 5.5 7.3 9.5-1.1 3.1-4.9 3.5-5.3 7.4Z"
        stroke={smoke}
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M19.1 35.2c2.3-4.1 6.4-6.5 11-6.5h4.6c.5 4.1 3 7.7 6.7 9.6-3 5.2-8.6 8.4-14.7 8.4H14.8c2.3-2.5 3.5-5.3 3.6-8.4l.7-3.1Z"
        stroke={ink}
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M35 31.5c6.1.3 10.3-1.8 13.8-6.3-.2 7.1-3.3 11.2-9.2 12.4" stroke={ink} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18.1 36.2h-4.9c-2.6 0-4.2 1.4-4.2 3.4 0 2.1 1.8 3.6 4.4 3.6h2.4" stroke={ink} strokeWidth="2.6" strokeLinecap="round" />
      <path d="M18 51h20.8" stroke={ink} strokeWidth="2.6" strokeLinecap="round" />
      <motion.path
        d="m50.8 11.5 1.1 3.1 3.1 1.1-3.1 1.1-1.1 3.1-1.1-3.1-3.1-1.1 3.1-1.1 1.1-3.1Z"
        fill={spark}
        animate={animated ? { scale: [0.8, 1.2, 0.8], opacity: [0.55, 1, 0.55] } : undefined}
        transition={animated ? { duration: 2.8, repeat: Infinity, ease: "easeInOut" } : undefined}
        style={{ transformOrigin: "50.8px 15.7px" }}
      />
    </motion.svg>
  )
}

export function ContentGenieLogo({
  variant = "lockup",
  size = "md",
  tone = "color",
  animated = false,
  className,
}: ContentGenieLogoProps) {
  return (
    <span
      className={cn("contentgenie-logo", `contentgenie-logo-${size}`, `contentgenie-logo-${tone}`, className)}
      aria-label={variant === "mark" ? "ContentGenie" : undefined}
    >
      <span className="logo-mark-wrap">
        <LampMark size={size} tone={tone} animated={animated} />
      </span>
      {variant === "lockup" && (
        <span className="logo-type" aria-label="ContentGenie">
          <strong aria-hidden="true">
            <span className="logo-content-word">CONTENT</span>
            <span className="logo-genie-word">GENIE</span>
          </strong>
          <small>Creative production studio</small>
        </span>
      )}
    </span>
  )
}
