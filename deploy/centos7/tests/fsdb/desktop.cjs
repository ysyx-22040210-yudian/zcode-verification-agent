// Native Electron acceptance. Pass port, workspace-relative FSDB and an optional retained wave ID.
const { createRequire } = require("node:module");
const { setTimeout: sleep } = require("node:timers/promises");
const { chromium } = createRequire("/home/verification-agent/zcode/packages/desktop/package.json")(
  "playwright-core",
);
async function run() {
  let browser;
  for (let i = 0; i < 60 && !browser; i++) {
    try {
      browser = await chromium.connectOverCDP("http://127.0.0.1:" + process.argv[2], { timeout: 800 });
    } catch {
      await sleep(650);
    }
  }
  if (!browser) throw new Error("No Electron session");
  try {
    let page;
    for (let i = 0; i < 60 && !page; i++) {
      page = browser
        .contexts()[0]
        ?.pages()
        .find((p) => p.url().includes("index.html?"));
      if (!page) await sleep(500);
    }
    let waveId = process.argv[4];
    if (process.argv[6] === "wide") {
      await page.getByTestId("fsdb-entry").click({ timeout: 45000 });
      await page.getByTestId("fsdb-job-input").fill(waveId);
      await page.getByTestId("fsdb-reopen").click();
      const viewer = page.frameLocator('[data-testid="fsdb-plot"]');
      const cursor = viewer.getByTestId("wave-cursor");
      for (const [tick, value] of [["9007199254740993", "1"], ["9007199254740994", "0"]]) {
        await cursor.fill(tick);
        await cursor.press("Enter");
        await viewer.locator('[data-signal="long.a"] [data-value]').filter({ hasText: new RegExp("^" + value + "$") }).waitFor();
        if (await cursor.inputValue() !== tick) throw new Error("Cursor rounded a timestamp");
      }
      console.log("NATIVE_FSDB_64BIT_CURSOR_VERIFIED", waveId);
      return;
    }
    if (process.argv[6] === "artifact") {
      const verify = page.getByTestId("verification-entry");
      await verify.waitFor({ timeout: 45000 });
      if (await verify.getAttribute("aria-pressed") !== "true") await verify.click();
      await page.getByTestId("verification-run-row").filter({ hasText: process.argv[7].slice(0, 8) }).click();
      await page.getByTestId("verification-waveform").filter({ hasText: "fsdb/demo.fsdb" }).click();
      await page.getByTestId("fsdb-path").waitFor();
      const source = await page.getByTestId("fsdb-path").inputValue();
      if (!source.endsWith("/" + process.argv[7] + "/evidence/fsdb/demo.fsdb")) throw new Error("Wrong run FSDB path");
      await page.getByTestId("fsdb-search").click();
      await page.getByRole("checkbox", { name: "wave_demo.data", exact: true }).check();
      await page.getByTestId("fsdb-read").click();
      await page.frameLocator('[data-testid="fsdb-plot"]').locator('[data-signal="wave_demo.data"]').waitFor();
      console.log("NATIVE_RUN_ARTIFACT_WINDOW_VERIFIED", process.argv[7]);
      return;
    }
    if (process.argv[6] === "chat") {
      const verification = page.getByTestId("verification-entry");
      await verification.waitFor({ timeout: 45000 });
      if ((await verification.getAttribute("aria-pressed")) === "true") await verification.click();
      await page.locator('[contenteditable="true"]').first().click();
      await page.keyboard.insertText(
        "在 demo.fsdb 查时钟、valid 和 data，找第 6 tick 之后 wave_demo.clk 的上升沿，提前 7 tick、延后 3 tick 提取波形，返回查询 ID。",
      );
      await page
        .getByRole("button", { name: /^(Send|发送)$/ })
        .first()
        .click();
      const answer = page.getByText(/FSDB_CHAT_JOB\s+[a-f0-9]{32}/).last();
      const deadline = Date.now() + 130000;
      while (!(await answer.isVisible()) && Date.now() < deadline) {
        const allow = page.getByText(/^(Allow only this time|仅允许本次|仅允许一次)$/).first();
        if (await allow.isVisible()) {
          await allow.click();
          const confirm = page.getByRole("button", { name: /^(Confirm|确认|确定)$/ }).last();
          if (await confirm.isVisible()) await confirm.click({ timeout: 1500 }).catch(() => {});
        }
        await sleep(300);
      }
      waveId = (await answer.innerText({ timeout: 2000 })).match(/FSDB_CHAT_JOB\s+([a-f0-9]{32})/)[1];
      console.log("AGENT_FSDB_JOB", waveId);
    }
    await page.getByTestId("fsdb-entry").click({ timeout: 45000 });
    await page.getByTestId("fsdb-path").fill(process.argv[3]);
    await page.getByTestId("fsdb-search").click();
    for (const name of ["wave_demo.clk", "wave_demo.valid", "wave_demo.data", "wave_demo.stable"]) {
      await page.getByRole("checkbox", { name, exact: true }).check();
    }
    await page.getByTestId("fsdb-read").click();
    const viewer = page.frameLocator('[data-testid="fsdb-plot"]');
    await viewer.locator('[data-signal="wave_demo.data"]').waitFor();
    await viewer.getByTestId("wave-cursor").fill("9");
    await viewer.getByTestId("wave-cursor").press("Enter");
    await viewer
      .locator('[data-signal="wave_demo.data"] [data-value]')
      .filter({ hasText: "10xz0011" })
      .waitFor();
    await viewer.getByTestId("wave-zoom-in").click();
    await viewer.getByTestId("wave-fit").click();
    if (waveId) {
      await page.getByTestId("fsdb-job-input").fill(waveId);
      await page.getByTestId("fsdb-reopen").click();
      await page.getByTestId("fsdb-job-id").filter({ hasText: waveId }).waitFor();
      await viewer.locator('[data-signal="wave_demo.data"]').waitFor();
    }
    await page.getByTestId("fsdb-detach").click();
    let detached;
    for (let i = 0; i < 50 && !detached; i++) {
      for (const p of browser.contexts()[0].pages()) {
        if (p !== page && (await p.getByTestId("wave-cursor").count())) {
          detached = p;
          break;
        }
      }
      if (!detached) await sleep(350);
    }
    if (!detached) throw new Error("No detached waveform window");
    await detached.getByTestId("wave-cursor").fill("15");
    await detached.getByTestId("wave-cursor").press("Enter");
    await detached
      .locator('[data-signal="wave_demo.valid"] [data-value]')
      .filter({ hasText: /^z$/i })
      .waitFor();
    if (process.argv[5]) await detached.screenshot({ path: process.argv[5] });
    console.log("NATIVE_FSDB_WINDOW_VERIFIED", await page.getByTestId("fsdb-job-id").innerText());
  } finally {
    await (await browser.newBrowserCDPSession()).send("Browser.close").catch(() => {});
    await browser.close();
  }
}
run().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
