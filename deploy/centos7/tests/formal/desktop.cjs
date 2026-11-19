// Drive a native Electron window started with the FIFO workspace and a disposable profile.
const { createRequire } = require("node:module");
const path = require("node:path");
const { setTimeout: sleep } = require("node:timers/promises");
const { chromium } = createRequire(path.resolve(__dirname, "../../../../packages/desktop/package.json"))("playwright-core");

async function main() {
  const [port, screenshot] = process.argv.slice(2);
  let browser;
  for (let attempt = 0; attempt < 100 && !browser; attempt++) {
    try { browser = await chromium.connectOverCDP("http://127.0.0.1:" + port, { timeout: 900 }); }
    catch { await sleep(400); }
  }
  if (!browser) throw new Error("Could not reach the test Electron instance");
  try {
    let page;
    for (let attempt = 0; attempt < 120 && !page; attempt++) {
      page = browser.contexts()[0].pages().find(p => p.url().includes("index.html?"));
      if (!page) await sleep(400);
    }
    const profile = page.getByTestId("verification-profile");
    await profile.selectOption("formal");
    await page.getByTestId("verification-variant").selectOption("mutant");
    await page.getByTestId("verification-submit").click();
    await page.getByTestId("verification-run-status").filter({hasText: /^fail$/}).waitFor({timeout: 120000});
    await page.getByTestId("verification-properties").getByRole("button", {name: /反例|counterexample/i}).click();
    await page.getByTestId("verification-evidence").locator("canvas").waitFor();
    console.log("Native Formal counterexample", await page.getByTestId("verification-run-id").innerText());
    await page.screenshot({path: screenshot});
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

