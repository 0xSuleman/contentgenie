"use client"

import { motion, useReducedMotion, useScroll, useTransform } from "motion/react"

const PARTICLES = [
  { x: 7, y: 18, size: 8, lift: 28, drift: 12, duration: 10, delay: 0, kind: "spark" },
  { x: 15, y: 70, size: 6, lift: 42, drift: -10, duration: 14, delay: 2, kind: "mote" },
  { x: 25, y: 34, size: 11, lift: 34, drift: 17, duration: 16, delay: 4, kind: "smoke" },
  { x: 34, y: 87, size: 7, lift: 32, drift: -15, duration: 12, delay: 1, kind: "spark" },
  { x: 45, y: 16, size: 5, lift: 24, drift: 9, duration: 11, delay: 5, kind: "mote" },
  { x: 57, y: 72, size: 13, lift: 48, drift: 15, duration: 18, delay: 3, kind: "smoke" },
  { x: 66, y: 28, size: 7, lift: 31, drift: -12, duration: 13, delay: 1.5, kind: "spark" },
  { x: 74, y: 83, size: 5, lift: 26, drift: 13, duration: 11, delay: 4.5, kind: "mote" },
  { x: 84, y: 42, size: 10, lift: 44, drift: -17, duration: 17, delay: 2.5, kind: "smoke" },
  { x: 93, y: 67, size: 8, lift: 36, drift: 10, duration: 14, delay: 0.5, kind: "spark" },
  { x: 21, y: 92, size: 5, lift: 22, drift: 8, duration: 9, delay: 3.5, kind: "mote" },
  { x: 89, y: 12, size: 6, lift: 30, drift: -9, duration: 12, delay: 6, kind: "mote" },
]

export function AmbientStage() {
  const reducedMotion = useReducedMotion()
  const { scrollY } = useScroll()
  const curveY = useTransform(scrollY, [0, 900], [0, reducedMotion ? 0 : 90])
  const orbY = useTransform(scrollY, [0, 900], [0, reducedMotion ? 0 : -55])

  return (
    <div className="ambient-stage" aria-hidden="true">
      <motion.div
        className="ambient-orb ambient-orb-periwinkle"
        style={{ y: orbY }}
        animate={reducedMotion ? undefined : { x: [0, 34, -18, 0], scale: [1, 1.08, 0.96, 1] }}
        transition={{ duration: 24, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="ambient-orb ambient-orb-sage"
        animate={reducedMotion ? undefined : { x: [0, -28, 16, 0], y: [0, 22, -12, 0] }}
        transition={{ duration: 29, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="ambient-orb ambient-orb-apricot"
        animate={reducedMotion ? undefined : { scale: [0.96, 1.1, 0.96], rotate: [0, 12, 0] }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="genie-particles">
        {PARTICLES.map((particle, index) => (
          <motion.i
            key={`${particle.kind}-${index}`}
            className={`genie-particle particle-${particle.kind}`}
            style={{ left: `${particle.x}%`, top: `${particle.y}%`, width: particle.size, height: particle.size }}
            animate={reducedMotion ? undefined : {
              x: [0, particle.drift, 0],
              y: [0, -particle.lift, 0],
              rotate: [0, particle.kind === "smoke" ? 35 : 180, 360],
              opacity: [0.12, 0.52, 0.12],
            }}
            transition={{ duration: particle.duration, delay: particle.delay, repeat: Infinity, ease: "easeInOut" }}
          />
        ))}
      </div>
      <motion.svg className="ambient-smoke ambient-smoke-one" viewBox="0 0 720 460" style={{ y: curveY }}>
        <path d="M14 383c123-5 134-112 260-118 109-5 126 84 237 68 103-15 91-131 198-146" />
        <path d="M85 434c80-40 90-114 181-141 86-25 142 25 224-22 78-44 94-126 173-160" />
      </motion.svg>
      <motion.svg className="ambient-smoke ambient-smoke-two" viewBox="0 0 520 520" style={{ y: orbY }}>
        <path d="M85 488c-24-111 101-132 68-237-27-87-91-110-42-184" />
        <path d="M142 519c-14-94 107-137 92-229-12-72-73-110-26-208" />
      </motion.svg>
      <span className="ambient-grain" />
    </div>
  )
}
