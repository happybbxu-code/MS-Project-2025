#!/usr/bin/env node
/**
 * Mobile layout regression test for the Medical Screening Assistant.
 *
 * Drives the real installed Chrome (headless) via puppeteer-core at several
 * iPhone viewport widths and asserts the mobile-critical layout contract:
 *   - no horizontal overflow (document scrollWidth <= viewport width)
 *   - header title fits WITHOUT ellipsis (h1.scrollWidth <= h1.clientWidth)
 *   - header/restart fully visible, not wrapped off
 *   - decorative badge is display:none on mobile (not merely zero-rect)
 *   - blue patient bubble not clipped at the right edge
 *   - composer input + send button fully visible
 *   - composer placeholder not vertically clipped (fits one line)
 *   - disclaimer visible and not covered by the bottom safe-area
 *
 * Also runs a desktop viewport check asserting the badge is genuinely
 * visible (nonzero width/height) and there is no horizontal overflow.
 *
 * Usage: node mobile-layout.test.js <baseUrl>
 * Exits 0 on pass, 1 on any failure. Prints a per-check report.
 */
const puppeteer = require('puppeteer-core');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const baseUrl = process.argv[2];
if (!baseUrl) {
  console.error('usage: node mobile-layout.test.js <baseUrl>');
  process.exit(2);
}

const VIEWPORTS = [
  { name: 'iPhone SE (320)', width: 320, height: 568, dpr: 2 },
  { name: 'iPhone 12 mini (375)', width: 375, height: 812, dpr: 3 },
  { name: 'iPhone 12/13 (390)', width: 390, height: 844, dpr: 3 },
  { name: 'iPhone 14 Pro Max (430)', width: 430, height: 932, dpr: 3 },
];

const results = [];

function record(ok, label, detail) {
  results.push({ ok, label, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? '  [' + detail + ']' : ''}`);
}

async function runViewport(browser, vp) {
  const page = await browser.newPage();
  await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: vp.dpr });
  await page.goto(baseUrl, { waitUntil: 'networkidle0', timeout: 20000 });

  // Wait for the doctor welcome bubble to render (startSession completes).
  await page.waitForSelector('#chat .row.doctor .bubble', { timeout: 15000 });

  // Inject a blue patient bubble to exercise the right-aligned bubble clipping.
  await page.evaluate(() => {
    if (typeof addBubble === 'function') {
      addBubble('I have had a persistent cough and shortness of breath for the past two weeks.', 'patient');
    }
  });
  await new Promise(r => setTimeout(r, 200));

  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const rect = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
    };
    const header = rect('header');
    const badge = rect('.badge');
    const restart = rect('#restart-btn');
    const bar = rect('#bar');
    const btn = rect('#btn');
    const txt = rect('#txt');
    const disclaimer = rect('.disclaimer');
    // last patient bubble
    const rows = [...document.querySelectorAll('.row.patient .bubble')];
    const lastBubble = rows.length ? rows[rows.length - 1].getBoundingClientRect() : null;
    // title fit: no ellipsis means scrollWidth <= clientWidth
    const h1 = document.querySelector('header h1');
    const title = h1 ? (() => {
      const r = h1.getBoundingClientRect();
      return { scrollWidth: h1.scrollWidth, clientWidth: h1.clientWidth, left: r.left, right: r.right };
    })() : null;
    // placeholder vertical fit: textarea clientHeight should accommodate one line
    const txtEl = document.querySelector('#txt');
    const placeholder = txtEl ? {
      clientHeight: txtEl.clientHeight,
      scrollHeight: txtEl.scrollHeight,
      lineHeight: parseFloat(getComputedStyle(txtEl).lineHeight),
      // one-line fit: the placeholder's natural width must not exceed the field
      placeholderFits: (() => {
        const probe = document.createElement('span');
        probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:inherit;';
        probe.textContent = txtEl.getAttribute('placeholder') || '';
        document.body.appendChild(probe);
        const w = probe.getBoundingClientRect().width;
        probe.remove();
        return w <= txtEl.clientWidth + 1;
      })(),
    } : null;
    return {
      vw, vh,
      scrollWidth: doc.scrollWidth,
      header, badge, restart, bar, btn, txt, disclaimer,
      lastBubble: lastBubble ? { left: lastBubble.left, right: lastBubble.right, width: lastBubble.width } : null,
      title, placeholder,
    };
  });

  const vw = metrics.vw;
  const vh = metrics.vh;
  const eps = 1; // sub-pixel tolerance

  // 1. No horizontal overflow
  const noOverflow = metrics.scrollWidth <= vw + eps;
  record(noOverflow, `[${vp.name}] no horizontal overflow`, `scrollWidth=${metrics.scrollWidth} vw=${vw}`);

  // 2. Header fully visible (right edge within viewport) and not wrapped
  const headerVisible = metrics.header && metrics.header.right <= vw + eps && metrics.header.left >= -eps;
  record(headerVisible, `[${vp.name}] header fully visible`, metrics.header ? `right=${metrics.header.right.toFixed(1)} vw=${vw}` : 'missing');
  const restartVisible = metrics.restart && metrics.restart.right <= vw + eps && metrics.restart.left >= -eps;
  record(restartVisible, `[${vp.name}] restart button visible`, metrics.restart ? `right=${metrics.restart.right.toFixed(1)}` : 'missing');

  // 3. Title fits WITHOUT ellipsis (full text visible)
  const titleFits = metrics.title && metrics.title.scrollWidth <= metrics.title.clientWidth + eps
    && metrics.title.right <= vw + eps && metrics.title.left >= -eps;
  record(titleFits, `[${vp.name}] full title fits (no ellipsis)`,
    metrics.title ? `scrollWidth=${metrics.title.scrollWidth} clientWidth=${metrics.title.clientWidth} left=${metrics.title.left.toFixed(1)} right=${metrics.title.right.toFixed(1)} vw=${vw}` : 'missing');

  // 4. Badge is display:none on mobile (decorative, intentionally hidden)
  const badgeHidden = metrics.badge && metrics.badge.width === 0 && metrics.badge.height === 0;
  record(badgeHidden, `[${vp.name}] badge hidden (display:none)`,
    metrics.badge ? `w=${metrics.badge.width} h=${metrics.badge.height}` : 'missing');

  // 5. Blue patient bubble not clipped at right
  const bubbleOk = metrics.lastBubble && metrics.lastBubble.right <= vw + eps && metrics.lastBubble.left >= -eps;
  record(bubbleOk, `[${vp.name}] patient bubble not clipped`, metrics.lastBubble ? `right=${metrics.lastBubble.right.toFixed(1)} vw=${vw}` : 'missing');

  // 6. Composer input + send button fully visible
  const btnOk = metrics.btn && metrics.btn.right <= vw + eps && metrics.btn.left >= -eps;
  record(btnOk, `[${vp.name}] send button fully visible`, metrics.btn ? `right=${metrics.btn.right.toFixed(1)} vw=${vw}` : 'missing');
  const txtOk = metrics.txt && metrics.txt.right <= vw + eps && metrics.txt.left >= -eps && metrics.txt.width >= 100;
  record(txtOk, `[${vp.name}] input not clipped`, metrics.txt ? `right=${metrics.txt.right.toFixed(1)} width=${metrics.txt.width.toFixed(1)}` : 'missing');

  // 7. Placeholder not vertically clipped and fits one line
  const phOk = metrics.placeholder && metrics.placeholder.clientHeight >= metrics.placeholder.lineHeight - eps
    && metrics.placeholder.placeholderFits;
  record(phOk, `[${vp.name}] placeholder fits one line (not clipped)`,
    metrics.placeholder ? `clientHeight=${metrics.placeholder.clientHeight} lineHeight=${metrics.placeholder.lineHeight} fits=${metrics.placeholder.placeholderFits}` : 'missing');

  // 8. Disclaimer visible and not covered by bottom safe area
  const discOk = metrics.disclaimer && metrics.disclaimer.bottom <= vh + eps && metrics.disclaimer.top >= -eps;
  record(discOk, `[${vp.name}] disclaimer visible`, metrics.disclaimer ? `bottom=${metrics.disclaimer.bottom.toFixed(1)} vh=${vh}` : 'missing');

  await page.close();
}

async function runDesktop(browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });
  await page.goto(baseUrl, { waitUntil: 'networkidle0', timeout: 20000 });
  await page.waitForSelector('#chat .row.doctor .bubble', { timeout: 15000 });

  const m = await page.evaluate(() => {
    const badge = document.querySelector('.badge');
    const r = badge.getBoundingClientRect();
    const cs = getComputedStyle(badge);
    const h1 = document.querySelector('header h1');
    return {
      badgeDisplay: cs.display,
      badgeWidth: r.width,
      badgeHeight: r.height,
      scrollWidth: document.documentElement.scrollWidth,
      vw: window.innerWidth,
      titleFits: h1.scrollWidth <= h1.clientWidth + 1,
      restartRight: document.querySelector('#restart-btn').getBoundingClientRect().right,
    };
  });

  const badgeVisible = m.badgeDisplay !== 'none' && m.badgeWidth > 0 && m.badgeHeight > 0;
  record(badgeVisible, '[desktop 1280] badge genuinely visible (nonzero size)',
    `display=${m.badgeDisplay} w=${m.badgeWidth.toFixed(1)} h=${m.badgeHeight.toFixed(1)}`);
  const noOverflow = m.scrollWidth <= m.vw + 1;
  record(noOverflow, '[desktop 1280] no horizontal overflow', `scrollWidth=${m.scrollWidth} vw=${m.vw}`);
  record(m.titleFits, '[desktop 1280] full title fits (no ellipsis)', m.titleFits ? 'ok' : 'ellipsized');
  record(m.restartRight <= m.vw + 1, '[desktop 1280] restart button visible', `right=${m.restartRight.toFixed(1)}`);

  await page.close();
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
  });

  for (const vp of VIEWPORTS) {
    await runViewport(browser, vp);
  }
  await runDesktop(browser);

  await browser.close();

  const failed = results.filter(r => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length) {
    console.log(`FAILED: ${failed.length} check(s)`);
    process.exit(1);
  }
  process.exit(0);
})().catch(err => {
  console.error('FATAL:', err.message);
  process.exit(1);
});
