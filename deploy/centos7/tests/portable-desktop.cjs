// Exercise a downloaded CentOS desktop through the real workbench.
const { createRequire } = require("node:module");
const path = require("node:path");
const fs = require("node:fs/promises");
const { setTimeout: sleep } = require("node:timers/promises");
const { chromium } = createRequire(path.resolve(__dirname, "../../../packages/desktop/package.json"))("playwright-core");

async function main() {
  const [port, output, previous] = process.argv.slice(2);
  let browser;
  for (let i = 0; i < 360 && !browser; i++) {
    try { browser = await chromium.connectOverCDP("http://127.0.0.1:" + port, {timeout: 1500}); }
    catch { await sleep(1000); }
  }
  if (!browser) throw new Error("The portable Electron desktop did not open");
  try {
    const context = browser.contexts()[0];
    let page;
    for (let i = 0; i < 180 && !page; i++) {
      page = context.pages().find(candidate => candidate.url().includes("index.html?"));
      if (!page) await sleep(1000);
    }
    if (!page) throw new Error("The main window did not load");
    const id = page.getByTestId("verification-run-id");
    const profile = page.getByTestId("verification-profile");
    await profile.waitFor({timeout: 360000});
    if (previous) {
      const expected = JSON.parse(await fs.readFile(previous, "utf8"));
      await page.getByTestId("verification-run-row").filter({hasText: expected.mutant.slice(0, 8)}).click({timeout: 60000});
      await id.filter({hasText: expected.mutant}).waitFor({timeout: 60000});
      await page.getByTestId("verification-properties").getByRole("button", {name: /反例|counterexample/i}).click();
      await page.getByTestId("verification-evidence").locator("canvas").waitFor({timeout: 60000});
      console.log("Restored FIFO run and counterexample", expected.mutant);
    } else {
      const receipt = {};
      for (const [variant, status] of [["normal", "pass"], ["mutant", "fail"]]) {
        await profile.selectOption("formal");
        await page.getByTestId("verification-variant").selectOption(variant);
        await page.getByTestId("verification-submit").click();
        await page.getByTestId("verification-run-status").filter({hasText: new RegExp("^" + status + "$")}).waitFor({timeout: 180000});
        receipt[variant] = (await id.innerText()).trim();
        if (!/^[0-9a-f]{32}$/i.test(receipt[variant])) throw new Error("Unexpected verification run ID");
      }
      await page.getByTestId("verification-properties").getByRole("button", {name: /反例|counterexample/i}).click();
      await page.getByTestId("verification-evidence").locator("canvas").waitFor({timeout: 60000});
      await page.screenshot({path: output + ".png"});
      await fs.writeFile(output + ".json", JSON.stringify(receipt, null, 2) + "\n");
      console.log("Verified portable FIFO", receipt);
    }
    const session = await browser.newBrowserCDPSession();
    await session.send("Browser.close").catch(() => {});
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
