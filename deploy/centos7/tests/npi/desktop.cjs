// Run with an isolated native desktop open on the test workspace and its CDP port.
const { createRequire } = require("node:module");
const { setTimeout: sleep } = require("node:timers/promises");
const { chromium } = createRequire("/home/verification-agent/zcode/packages/desktop/package.json")("playwright-core");

async function check() {
  let browser;
  for (let i = 0; i < 60 && !browser; i++) {
    try { browser = await chromium.connectOverCDP("http://127.0.0.1:" + process.argv[2], { timeout: 900 }); }
    catch { await sleep(600); }
  }
  if (!browser) throw new Error("No native desktop CDP connection");
  try {
    let page;
    for (let i = 0; i < 60 && !page; i++) {
      page = browser.contexts()[0]?.pages().find((p) => p.url().includes("index.html?"));
      if (!page) await sleep(500);
    }
    if (process.argv[5] === "chat") {
      const verify = page.getByTestId("verification-entry");
      await verify.waitFor({ timeout: 45000 });
      if (await verify.getAttribute("aria-pressed") === "true") await verify.click();
      const input = page.locator('[contenteditable="true"]').first();
      await input.click();
      await page.keyboard.insertText("请用 build/simv.daidir/simv.kdb 查 npi_demo.lane[0].u_tx.port.valid 的 driver 和 loader，返回查询 ID。");
      await page.getByRole("button", { name: /^(Send|发送)$/ }).first().click();
      const answer = page.getByText(/NPI_CHAT_JOB\s+[a-f0-9]{32}/).last();
      const deadline = Date.now() + 120000;
      while (!await answer.isVisible() && Date.now() < deadline) {
        const allow = page.getByText(/^(Allow only this time|仅允许本次|仅允许一次)$/).first();
        if (await allow.isVisible()) {
          await allow.click();
          const confirm = page.getByRole("button", { name: /^(Confirm|确认|确定)$/ }).last();
          if (await confirm.isVisible()) await confirm.click({ timeout: 1600 }).catch(() => {});
        }
        await sleep(350);
      }
      const text = await answer.innerText({ timeout: 2000 });
      const id = text.match(/NPI_CHAT_JOB\s+([a-f0-9]{32})/)[1];
      await page.getByTestId("design-query-entry").click();
      await page.getByRole("textbox", { name: /按查询 ID 打开|Open query by ID/ }).fill(id);
      await page.getByRole("button", { name: /^(Open|打开)$/ }).click();
      await page.getByTestId("design-query-loads").getByText("npi_demo.lane[0].u_relay.u_tap", { exact: true }).waitFor();
      if ((await page.getByTestId("design-query-job-id").innerText()).trim() !== id) throw new Error("Desktop ID differs from chat");
      if (await page.getByTestId("design-query-operation").inputValue() !== "signal" ||
          await page.getByTestId("design-query-signal").inputValue() !== "npi_demo.lane[0].u_tx.port.valid" ||
          await page.getByTestId("design-query-kdb").inputValue() !== "build/simv.daidir/simv.kdb") throw new Error("Opened query inputs differ from the submitted request");
      console.log("NATIVE_AGENT_DESKTOP_SHARED_RESULT", id);
      if (process.argv[4]) await page.screenshot({ path: process.argv[4] });
      return;
    }
    await page.getByTestId("design-query-entry").click({ timeout: 45000 });
    await page.getByTestId("design-query-kdb").fill(process.argv[3] || "build/simv.daidir/simv.kdb");
    await page.getByTestId("design-query-pattern").fill("sender");
    await page.getByTestId("design-query-start").click();
    await page.getByTestId("design-query-result").getByText("npi_demo.lane[1].u_tx", { exact: true }).waitFor();
    await page.getByTestId("design-query-operation").selectOption("signal");
    await page.getByTestId("design-query-signal").fill("npi_demo.lane[0].u_tx.port.valid");
    await page.getByTestId("design-query-start").click();
    const result = page.getByTestId("design-query-result");
    await result.getByTestId("design-query-loads").getByText("npi_demo.lane[0].u_relay.u_tap", { exact: true }).waitFor();
    await result.getByTestId("design-query-drivers").getByText("npi_demo.lane[0].u_tx", { exact: true }).waitFor();
    const id = (await page.getByTestId("design-query-job-id").innerText()).trim();
    if (!/^[a-f0-9]{32}$/.test(id)) throw new Error("Missing query ID");
    console.log("NATIVE_DESKTOP_NPI_VERIFIED", id);
    if (process.argv[4]) await page.screenshot({ path: process.argv[4] });
  } finally {
    await (await browser.newBrowserCDPSession()).send("Browser.close").catch(() => {});
    await browser.close();
  }
}
check().catch((err) => { console.error(err); process.exitCode = 1; });

