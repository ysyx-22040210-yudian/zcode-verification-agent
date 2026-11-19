// Exercise the same model and same conversation through the real desktop settings and composer.
const assert = require("node:assert/strict");
const { dirname, join } = require("node:path");

module.exports = async function verifyVision(page, awaitAnswer, screenshot) {
  async function setVision(enabled) {
    await page.getByTestId("task-settings-button").click();
    await page.getByTestId("settings-section-nav-modelProvider").click();
    await page.getByTestId("model-provider-nav-item-custom:verification-e2e").click();
    await page.locator('[data-model-provider-model-id="verification-tool-test"] button:has(svg.lucide-pencil)').click();
    const dialog = page.getByRole("dialog").last();
    const advanced = dialog.locator("[data-model-advanced-trigger]");
    if (await advanced.getAttribute("aria-expanded") === "false") await advanced.click();
    const vision = dialog.locator('[data-model-input-modality="image"]');
    await vision.waitFor({ state: "visible" });
    assert.match(await vision.textContent(), /视觉模型|vision model/i);
    assert.equal(await vision.getAttribute("aria-pressed"), String(!enabled));
    await vision.click();
    assert.equal(await vision.getAttribute("aria-pressed"), String(enabled));
    if (!enabled) await page.screenshot({ path: join(dirname(screenshot), "model-vision-settings.png") });
    await dialog.getByRole("button", { name: /^(保存|Save)$/ }).click();
    await dialog.waitFor({ state: "hidden" });
    await page.getByTestId("settings-back-button").click();
  }

  async function send(phase, paste) {
    const editor = page.locator('[contenteditable="true"]').first();
    await editor.click();
    if (paste) {
      await editor.evaluate(async (element) => {
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 24;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#397dc1";
        ctx.fillRect(0, 0, 24, 24);
        const png = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
        const clipboardData = new DataTransfer();
        clipboardData.items.add(new File([png], "vision-probe.png", { type: "image/png" }));
        element.dispatchEvent(new ClipboardEvent("paste", { clipboardData, bubbles: true, cancelable: true }));
      });
      await page.locator('[data-testid^="v4-attachment-"]').last().waitFor({ timeout: 10000 });
    }
    await page.keyboard.insertText("VISION_CASE_" + phase + " 读取 NPI 原始手册第 1 页，并保留此句文本。");
    await page.getByRole("button", { name: /^(Send|发送)$/ }).first().click();
    const answer = await awaitAnswer(page, new RegExp("VISION_WIRE_" + phase + "_(?:OK|FAIL)"), "MODEL_VISION");
    assert.ok(answer.includes("VISION_WIRE_" + phase + "_OK"), answer);
  }

  for (const [phase, enabled, paste] of [["OFF", false, true], ["ON", true, true], ["REPLAY", false, false]]) {
    await setVision(enabled);
    await send(phase, paste);
  }
};
