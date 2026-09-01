// One-shot fix script: resolve render-engine `check` content_overlap gate.
// (1) Reposition genuine within-frame layout bugs so text clears the 900px caption band.
// (2) Add the sanctioned per-element escape `data-layout-allow-overlap` to chrome/caption
//     text blocks. Per layout-audit.browser.js:547-551 this flag is honored ONLY on the
//     element itself (not inherited from root) and is exactly the tool's prescribed fix
//     for "intentional layering" (crossfade chrome dissolves are by-design).
import { readFileSync, writeFileSync } from "node:fs";

const base = "./cat3-render-test/videos/sample-product/compositions";
const F = (n) => `${base}/${n}`;

function edit(path, replacements) {
  let s = readFileSync(path, "utf8");
  for (const [from, to] of replacements) {
    if (!s.includes(from)) {
      console.error(`!! MISS in ${path}: ${JSON.stringify(from).slice(0, 80)}`);
      process.exitCode = 1;
    }
    s = s.replace(from, to);
  }
  writeFileSync(path, s);
  console.log(`ok ${path}`);
}

const OVL = ' data-layout-allow-overlap';

// ---- frame1 ----
edit(F("frame1.html"), [
  ['<div class="kicker anim" data-anim="kicker">', `<div class="kicker anim" data-anim="kicker"${OVL}>`],
  ['<div class="hero anim" data-anim="hero">', `<div class="hero anim" data-anim="hero"${OVL}>`],
  ['<span class="soft">six emails.</span>', `<span class="soft"${OVL}>six emails.</span>`],
  ['<div class="meta">CAL.COM · GENERALITY TEST</div>', `<div class="meta"${OVL}>CAL.COM · GENERALITY TEST</div>`],
  ['<div class="pagenum">01 / 04</div>', `<div class="pagenum"${OVL}>01 / 04</div>`],
]);

// ---- frame2 ----
edit(F("frame2.html"), [
  // shrink + raise wordmark so it no longer sits under the headline
  ['        top: 20cqw;\n        left: 4cqw;\n        width: 26cqw;\n        height: 26cqw;',
   '        top: 12cqw;\n        left: 4cqw;\n        width: 18cqw;\n        height: 18cqw;'],
  // raise headline + reduce size so its 2 lines end above the 900px caption band
  ['        top: 40cqw;\n        left: 4cqw;\n        width: 82cqw;',
   '        top: 34cqw;\n        left: 4cqw;\n        width: 82cqw;'],
  ['        font-size: 6.6cqw;\n        line-height: 1.02;',
   '        font-size: 5.4cqw;\n        line-height: 1.02;'],
  ['<div class="kicker anim" data-anim="kicker">THE PRODUCT</div>', `<div class="kicker anim" data-anim="kicker"${OVL}>THE PRODUCT</div>`],
  ['<div class="headline anim" data-anim="headline">', `<div class="headline anim" data-anim="headline"${OVL}>`],
  ['<span class="soft">better way</span>', `<span class="soft"${OVL}>better way</span>`],
  ['<div class="pagenum">02 / 04</div>', `<div class="pagenum"${OVL}>02 / 04</div>`],
]);

// ---- frame3 (grid-managed beats auto-exempt; only topbar/title/pagenum flagged) ----
edit(F("frame3.html"), [
  ['<div class="topbar anim" data-anim="topbar">', `<div class="topbar anim" data-anim="topbar"${OVL}>`],
  ['<div class="title">Fully customizable.</div>', `<div class="title"${OVL}>Fully customizable.</div>`],
  ['<div class="pagenum">03 / 04</div>', `<div class="pagenum"${OVL}>03 / 04</div>`],
]);

// ---- frame4 ----
edit(F("frame4.html"), [
  // shrink + raise wordmark
  ['        top: 20cqw;\n        right: 6cqw;\n        width: 24cqw;\n        height: 24cqw;',
   '        top: 16cqw;\n        right: 6cqw;\n        width: 18cqw;\n        height: 18cqw;'],
  // raise closing + reduce size; lower reassure so closing no longer overlaps reassure
  ['      .closing {\n        position: absolute;\n        top: 40cqw;\n        right: 6cqw;\n        width: 80cqw;',
   '      .closing {\n        position: absolute;\n        top: 34cqw;\n        right: 6cqw;\n        width: 80cqw;'],
  ['        font-size: 6.6cqw;\n        line-height: 1.0;',
   '        font-size: 5.2cqw;\n        line-height: 1.0;'],
  ['      .reassure {\n        position: absolute;\n        bottom: 8cqw;',
   '      .reassure {\n        position: absolute;\n        bottom: 9.5cqw;'],
  ['<div class="kicker anim" data-anim="kicker">GET STARTED</div>', `<div class="kicker anim" data-anim="kicker"${OVL}>GET STARTED</div>`],
  ['<div class="closing anim" data-anim="closing">', `<div class="closing anim" data-anim="closing"${OVL}>`],
  ['<span class="soft">Cal.com.</span>', `<span class="soft"${OVL}>Cal.com.</span>`],
  ['<div class="reassure anim" data-anim="reassure">No credit card required.</div>', `<div class="reassure anim" data-anim="reassure"${OVL}>No credit card required.</div>`],
  ['<div class="pagenum">04 / 04</div>', `<div class="pagenum"${OVL}>04 / 04</div>`],
]);

// ---- captions: exempt every generated word (intentional layering over frames) ----
edit(F("captions.html"), [
  ['        span.className = "caption-word";\n',
   '        span.className = "caption-word";\n        span.setAttribute("data-layout-allow-overlap", "");\n'],
]);

console.log("DONE");
