// Native desktop acceptance with an isolated profile and real verification tools.
const { chromium } = require("node:module").createRequire(
  "/home/verification-agent/zcode/packages/desktop/package.json",
)("playwright-core");
const { setTimeout: sleep } = require("node:timers/promises");
async function awaitAnswer(page, pattern, label) {
  const answer = page.getByText(pattern).last();
  const deadline = Date.now() + 155000;
  while (!(await answer.isVisible()) && Date.now() < deadline) {
    const allow = page
      .getByText(/^(Allow only this time|仅允许这一次|仅允许本次|仅允许一次)$/)
      .first();
    if (await allow.isVisible()) {
      await allow.click();
      const confirm = page
        .getByRole("button", { name: /^(Confirm|确认|确定)$/ })
        .last();
      if (await confirm.isVisible())
        await confirm.click({ timeout: 1700 }).catch(() => {});
    }
    await sleep(300);
  }
  if (!(await answer.isVisible()))
    throw new Error(
      label +
        " did not finish: " +
        (await page.locator("body").innerText()).slice(-2000),
    );
  const text = await answer.innerText();
  console.log(label, text);
  return text;
}
async function run() {
  let browser;
  for (let i = 0; i < 80 && !browser; i++) {
    try {
      browser = await chromium.connectOverCDP(
        "http://127.0.0.1:" + process.argv[2],
        { timeout: 700 },
      );
    } catch {
      await sleep(450);
    }
  }
  if (!browser) throw new Error("Electron did not start");
  try {
    let page;
    for (let i = 0; i < 80 && !page; i++) {
      page = browser
        .contexts()[0]
        .pages()
        .find((p) => p.url().includes("index.html?"));
      if (!page) await sleep(350);
    }
    const entry = page.getByTestId("verification-tools-entry");
    await entry.waitFor({ timeout: 55000 });
    const verify = page.getByTestId("verification-entry");
    if ((await verify.getAttribute("aria-pressed")) === "true")
      await verify.click();
    if (process.argv[5] === "model-vision") {
      await require("../model-vision/desktop.cjs")(page, awaitAnswer, process.argv[3]);
      return;
    }
    const editor = page.locator('[contenteditable="true"]').first();
    await editor.click();
    await page.keyboard.insertText(
      "用 build/simv.daidir/simv.kdb 查 sender 的实例，看看 demo.fsdb 里 wave_demo.data 在 8 到 12 tick 怎样变化，再查 simv.vdb 合并视图里未命中的 FSM 转移，给我三个查询 ID。",
    );
    await page
      .getByRole("button", { name: /^(Send|发送)$/ })
      .first()
      .click();
    const routed = await awaitAnswer(
      page,
      /TOOLKIT_ROUTED(?: [a-f0-9]{32}){3}/,
      "NATIVE_ORDINARY_CHAT",
    );
    await entry.click();
    const search = page.getByTestId("verification-tool-search");
    await page.getByTestId("tool-select-coverage").waitFor();
    if ((await page.locator('[data-testid^="tool-select-"]').count()) !== 3)
      throw new Error("Expected exactly three tools");
    if (process.argv[3]) await page.screenshot({ path: process.argv[3] });
    const request = page.getByTestId("tool-request");
    await request.fill("draft: inspect interface bindings");
    await search.fill("covergroup");
    await page.getByTestId("tool-select-coverage").click();
    await search.fill("");
    await page.getByTestId("tool-select-rtl").click();
    if ((await request.inputValue()) !== "draft: inspect interface bindings")
      throw new Error("Search lost the RTL request");
    for (const [alias, id, view] of [
      ["负载", "rtl", "design-query-panel"],
      ["触发前", "fsdb", "fsdb-path"],
      ["covergroup", "coverage", "coverage-input"],
    ]) {
      await search.fill(alias);
      await page.getByTestId("tool-select-" + id).click();
      await page.getByTestId("tool-open").click();
      await page.getByTestId(view).waitFor({ timeout: 10000 });
      if (id === "rtl") {
        const queryId = routed.match(/TOOLKIT_ROUTED ([a-f0-9]{32})/)[1];
        const kdb = page.getByTestId("design-query-kdb");
        const start = page.getByTestId("design-query-start");
        if (!(await start.isDisabled())) throw new Error("An empty KDB was accepted");
        await page.getByRole("textbox", { name: /按查询 ID 打开|Open query by ID/ }).fill(queryId);
        await page.getByRole("button", { name: /^(打开|Open)$/ }).click();
        await page.getByTestId("design-query-result").getByText("npi_demo.lane[1].u_tx", { exact: true }).waitFor();
        if (await kdb.inputValue() !== "build/simv.daidir/simv.kdb") throw new Error("Lost the original KDB path");
        // Pass the VM file path to Chromium. A Playwright upload can stage the descriptor without its companion KDB.
        const path = process.argv[4];
        const cdp = await page.context().newCDPSession(page);
        try {
          await cdp.send("Page.enable");
          await cdp.send("Page.setInterceptFileChooserDialog", { enabled: true });
          const [chosen] = await Promise.all([
            new Promise((resolve) => cdp.once("Page.fileChooserOpened", resolve)),
            page.getByTestId("design-query-browse").click(),
          ]);
          await cdp.send("DOM.setFileInputFiles", { backendNodeId: chosen.backendNodeId, files: [path] });
        } finally {
          await cdp.detach();
        }
        await page.waitForFunction((paths) => paths.includes(document.querySelector('[data-testid="design-query-kdb"]').value),
          [path, require("node:fs").realpathSync(path)], { timeout: 10000 }).catch(async (error) => {
            throw new Error(`Expected the selected VM KDB, received ${await kdb.inputValue()}: ${error.message}`);
          });
        await page.getByTestId("design-query-operation").selectOption("signal");
        await page.getByTestId("design-query-signal").fill("npi_demo.lane[0].u_tx.port.valid");
        await start.click();
        await page.getByTestId("design-query-drivers").getByText("npi_demo.lane[0].u_tx", { exact: true }).waitFor();
        await page.getByTestId("design-query-loads").getByText("npi_demo.lane[0].u_relay.u_tap", { exact: true }).waitFor();
        console.log("NATIVE_KDB_FILE_PICKER", await page.getByTestId("design-query-job-id").innerText());
        await page.screenshot({ path: require("node:path").join(require("node:path").dirname(process.argv[3]), "rtl-kdb-window.png") });
      }
      await entry.click();
    }
    await search.fill("nothing-matches-xyz");
    await page.getByTestId("tool-no-results").waitFor();
    await search.fill("fsdb_wave");
    const fsdb = page.getByTestId("tool-select-fsdb");
    await fsdb.focus();
    await fsdb.press("Enter");
    await page.getByTestId("tool-mode-develop").click();
    await page.getByTestId("tool-scaffold").click();
    await page
      .getByTestId("tool-starter-path")
      .filter({ hasText: "fsdb_edges.py" })
      .waitFor();
    await page
      .getByTestId("tool-request")
      .fill(
        "在当前工程基于 FSDB 工具编写 wave_report.py，统计 demo.fsdb 中 wave_demo.data 从 8 到 12 tick 变成含 X/Z 值的次数和具体时间，写入 unknown-edges.json 并运行验证。",
      );
    await page.getByTestId("tool-ask-agent").click();
    await awaitAnswer(
      page,
      /TOOLKIT_AGENT_EXTENSION [a-f0-9]{32}/,
      "NATIVE_TOOLS_AND_DEVELOPMENT",
    );
  } finally {
    await (await browser.newBrowserCDPSession())
      .send("Browser.close")
      .catch(() => {});
    await browser.close();
  }
}
run().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
