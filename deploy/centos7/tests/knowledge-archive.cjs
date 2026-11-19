// Native desktop acceptance against a running, isolated profile and test model.
const { createRequire } = require("node:module");
const { setTimeout: sleep } = require("node:timers/promises");
const { chromium } = createRequire("/home/verification-agent/zcode/packages/desktop/package.json")("playwright-core");
const [port, pdf, mode = "picker"] = process.argv.slice(2);

async function run() {
  let browser;
  for (let i = 0; i < 60 && !browser; i++) {
    try { browser = await chromium.connectOverCDP("http://127.0.0.1:" + port, { timeout: 900 }); }
    catch { await sleep(700); }
  }
  if (!browser) throw new Error("No native desktop");
  try {
    let page;
    for (let i = 0; i < 45 && !page; i++) {
      page = browser.contexts()[0]?.pages().find((item) => item.url().includes("index.html?"));
      if (!page) await sleep(500);
    }
    if (!page) throw new Error("No workspace window");
    if (mode === "chat") {
      await page.getByTestId("verification-workbench").waitFor({ timeout: 45000 });
      await page.getByTestId("verification-entry").click();
      const input = page.locator('[contenteditable="true"]').first();
      await input.click();
      await page.keyboard.insertText("Import this PDF and file it in the knowledge base. " + JSON.stringify({ path: pdf }));
      await page.getByRole("button", { name: /^(Send|发送)$/ }).first().click();
    } else if (mode !== "restart") {
      await page.getByTestId("knowledge-entry").click({ timeout: 45000 });
      const session = await page.context().newCDPSession(page);
      const [chooser] = await Promise.all([
        page.waitForEvent("filechooser"), page.getByTestId("knowledge-import").click(),
      ]);
      if (chooser.isMultiple()) throw new Error("Expected a single local PDF");
      // Playwright can synthesize a File from bytes. Electron needs a real disk-backed selection.
      const { root } = await session.send("DOM.getDocument");
      const { nodeId } = await session.send("DOM.querySelector", {
        nodeId: root.nodeId, selector: '[data-testid="knowledge-import-file"]',
      });
      await session.send("DOM.setFileInputFiles", { nodeId, files: [pdf] });
    }
    if (mode === "offline") {
      await page.getByRole("alert").filter({ hasText: /Select a model|选择模型/ }).waitFor();
      await page.getByTestId("knowledge-source-metadata").filter({ hasText: "Offline Timing Fixture" }).waitFor();
      await page.getByTestId("knowledge-archive-status").filter({ hasText: /0\s*\/\s*2/ }).waitFor();
      await page.getByTestId("knowledge-query").fill("capture_edge");
      await page.getByTestId("knowledge-search").click();
      await page.getByTestId("knowledge-result").first().click();
      await page.getByTestId("knowledge-text").filter({ hasText: /capture_edge/ }).waitFor();
      console.log("NATIVE_OFFLINE_PDF_INDEXED_FILING_PENDING");
      return;
    }
    if (mode !== "restart") {
      const marker = page.getByText("ARCHIVE_CONVERSATION_VERIFIED", { exact: false }).last();
      const until = Date.now() + 150000;
      while (!(await marker.isVisible()) && Date.now() < until) {
        const allow = page.getByText(/^(Allow only this time|仅允许本次|仅允许一次)$/).first();
        if (await allow.isVisible()) {
          await allow.click();
          const confirm = page.getByRole("button", { name: /^(Confirm|确认|确定)$/ }).last();
          if (await confirm.isVisible()) await confirm.click({ timeout: 1200 }).catch(() => {});
        }
        await sleep(350);
      }
      await marker.waitFor({ timeout: 1500 });
    }
    await page.getByTestId("knowledge-entry").click();
    const source = page.getByTestId("knowledge-source");
    await source.selectOption({ label: mode === "picker" ? "Timing Reference Fixture" : "Chat Timing Fixture" });
    await page.getByTestId("knowledge-archive-status").filter({ hasText: /2\s*\/\s*2/ }).waitFor();
    await page.getByTestId("knowledge-query").fill("采样时刻");
    await page.getByTestId("knowledge-search").click();
    await page.getByTestId("knowledge-result").first().click();
    await page.getByTestId("knowledge-text").filter({ hasText: /capture_edge/ }).waitFor();
    await page.getByTestId("knowledge-pdf-toggle").click();
    await page.locator('[data-testid="knowledge-pdf"] canvas').first().waitFor();
    console.log("NATIVE_MODEL_ARCHIVE_SEARCH_ORIGINAL entry=" + mode + " page=2");
  } finally {
    await (await browser.newBrowserCDPSession()).send("Browser.close").catch(() => {});
    await browser.close();
  }
}

run().catch((error) => { console.error(error); process.exitCode = 1; });

