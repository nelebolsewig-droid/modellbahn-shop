// Druckt das Stellwerk-Handbuch (handbuch.html) als PDF in die Hilfe des Stellwerks.
// Aufruf aus dem Repository: node docs/handbuch/pdf.mjs [ziel.pdf]
// Braucht Playwright mit Chromium und Internet für die Schriften (Google Fonts).
import { chromium } from "playwright";

const source = new URL("handbuch.html", import.meta.url).href;
const target =
  process.argv[2] ?? new URL("../../frontend/public/admin/hilfe/stellwerk-handbuch.pdf", import.meta.url).pathname;

const footer = `<div style="width:100%;font-family:Arial;font-size:7.5px;color:#5C524B;padding:0 16mm;display:flex;justify-content:space-between;-webkit-print-color-adjust:exact">
  <span><i style="font-family:'Times New Roman';color:#C8102E;font-weight:bold">adp</i><b style="color:#000">-Modelle</b> &nbsp;·&nbsp; Stellwerk-Handbuch</span>
  <span class="pageNumber"></span></div>`;

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(source, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.pdf({
  path: target,
  format: "A4",
  printBackground: true,
  preferCSSPageSize: true,
  displayHeaderFooter: true,
  headerTemplate: "<div></div>",
  footerTemplate: footer,
});
await browser.close();
console.log(`PDF geschrieben: ${target}`);
