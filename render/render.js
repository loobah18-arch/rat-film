#!/usr/bin/env node
/**
 * Frame capture: deterministic screenshots of index.html at fixed t values.
 * Every frame = paint(t) — the film is fully time-driven, so capture is exact.
 * Usage: node render/render.js   (env: FPS=24, DUR=64, W=1920, H=1080, OUT=frames)
 */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const FPS = parseInt(process.env.FPS || "24", 10);
const DUR = parseFloat(process.env.DUR || "64");
const OUT = process.env.OUT || "frames";
const W = parseInt(process.env.W || "1920", 10);
const H = parseInt(process.env.H || "1080", 10);
const URL =
  "file://" + path.resolve(__dirname, "..", "index.html") + "?render=1";

(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({
    args: ["--force-color-profile=srgb", "--disable-lcd-text", "--hide-scrollbars"],
  });
  const page = await browser.newPage({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
  });
  await page.goto(URL, { waitUntil: "load" });
  await page.waitForFunction("window.__READY === true", null, { timeout: 30000 });

  const total = Math.round(DUR * FPS);
  for (let i = 0; i < total; i++) {
    const t = i / FPS;
    await page.evaluate((tt) => window.__seek(tt), t);
    await page.screenshot({
      path: path.join(OUT, `f${String(i).padStart(5, "0")}.jpg`),
      type: "jpeg",
      quality: 92,
    });
    if (i % 96 === 0) console.log(`frame ${i}/${total} (t=${t.toFixed(2)}s)`);
  }
  await browser.close();
  console.log(`DONE ${total} frames -> ${OUT}/`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
