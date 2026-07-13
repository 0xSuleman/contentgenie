import { expect, test } from "@playwright/test"

test("floating navigation and command palette switch views", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("navigation", { name: "ContentGenie workspace" })).toBeVisible()
  await expect(page.getByRole("heading", { name: /Turn a spark into a/ })).toBeVisible()

  await page.getByRole("button", { name: "Media library" }).click()
  await expect(page.getByRole("heading", { name: /Build a visual library/ })).toBeVisible()

  await page.keyboard.press("Control+K")
  await expect(page.getByRole("dialog", { name: "ContentGenie quick find" })).toBeVisible()
  await page.getByPlaceholder(/Search Create/).fill("Settings")
  await page.getByRole("option", { name: /Settings/ }).click()
  await expect(page.getByRole("heading", { name: /Tune the atelier/ })).toBeVisible()
})

test("creative controls and dialogs remain keyboard accessible", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: /Creative direction/ }).click()
  await expect(page.getByRole("combobox", { name: "Audience" })).toBeVisible()

  await page.getByRole("button", { name: "Media library" }).click()
  await page.getByRole("button", { name: "Add asset" }).click()
  await expect(page.getByRole("dialog", { name: "Add a remote asset" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog", { name: "Add a remote asset" })).toBeHidden()
})

test("script-matched Creative Commons music is the default production mode", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: /Footage, music & rights/ }).click()
  const automaticMusic = page.getByRole("radio", { name: "Script match" })
  await expect(automaticMusic).toBeChecked()
  await expect(page.getByText(/finds CC0 or CC BY music that follows the script/)).toBeVisible()
  await expect(page.getByText("Library track")).toBeHidden()
})

test("production archive previews portrait video and exposes safe file actions", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: "Productions" }).click()
  await expect(page.getByRole("heading", { name: /Every finished Short/ })).toBeVisible()

  const preview = page.getByLabel(/Preview /)
  await expect(preview).toBeVisible()
  const dimensions = await preview.evaluate((video) => {
    const bounds = video.getBoundingClientRect()
    return { width: bounds.width, height: bounds.height }
  })
  expect(dimensions.width / dimensions.height).toBeCloseTo(9 / 16, 1)

  await expect(page.getByRole("link", { name: "Download video" })).toHaveAttribute("href", /\/api\/productions\/[a-f0-9]+\/download/)
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByRole("alertdialog", { name: "Delete this produced video?" })).toBeVisible()
  await expect(page.getByText(/permanently deleted from the backend/)).toBeVisible()
  await page.getByRole("button", { name: "Keep video" }).click()
})

test("navigation stays glassy and visible without covering scrolled option blocks", async ({ page }) => {
  await page.goto("/")
  const navigation = page.getByRole("navigation", { name: "ContentGenie workspace" })
  const voiceSection = page.getByRole("button", { name: /Voice & visual language/ })
  await voiceSection.click()
  await voiceSection.scrollIntoViewIfNeeded()
  await page.evaluate(() => window.scrollBy(0, 320))
  await expect(navigation).toBeInViewport()
  await expect(navigation.locator("..")).toHaveAttribute("data-scrolled", "true")
  await expect(page.getByRole("combobox", { name: "Voice personality" })).toBeInViewport()
})

for (const viewport of [
  { width: 1180, height: 900 },
  { width: 1440, height: 1200 },
  { width: 1920, height: 1080 },
]) {
  test(`desktop shell has no horizontal cutout at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto("/")
    const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }))
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport)
    await expect(page.getByRole("button", { name: "Settings" })).toBeInViewport()
  })
}

test("reduced motion disables ambient animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await page.goto("/")
  const duration = await page.locator(".ambient-orb-periwinkle").evaluate((element) => Number.parseFloat(getComputedStyle(element).animationDuration) || 0)
  expect(duration).toBeLessThanOrEqual(0.01)
})

test("Moonlit Paper semantic text colors meet WCAG AA", async ({ page }) => {
  await page.goto("/")
  const ratios = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement)
    const read = (name: string) => root.getPropertyValue(name).trim()
    const luminance = (color: string) => {
      const channels = color.match(/[\da-f]{2}/gi)!.map((channel) => Number.parseInt(channel, 16) / 255)
      const linear = channels.map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
      return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    }
    const contrast = (foreground: string, background: string) => {
      const light = Math.max(luminance(foreground), luminance(background))
      const dark = Math.min(luminance(foreground), luminance(background))
      return (light + 0.05) / (dark + 0.05)
    }
    return [
      contrast(read("--ink"), read("--canvas")),
      contrast(read("--quiet"), read("--canvas")),
      contrast(read("--faint"), read("--paper")),
      contrast(read("--periwinkle-deep"), read("--canvas")),
      contrast(read("--sage-deep"), read("--sage-soft")),
      contrast(read("--apricot-deep"), read("--paper")),
    ]
  })
  for (const ratio of ratios) expect(ratio).toBeGreaterThanOrEqual(4.5)
})
