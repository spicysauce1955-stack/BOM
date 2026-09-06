const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const output = process.env.SCREENSHOT_DIR || '/tmp/bom-journey-regression';
  fs.mkdirSync(output, { recursive: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (['error', 'warning'].includes(m.type())) errors.push(m.text()); });
    await page.goto(pathToFileURL(path.resolve(__dirname, '../index.html')).href);
    const step = i => page.locator(`[data-step="${i}"]`).click();
    const reset = () => page.locator('#restart').click();

    await step(1); await page.locator('#place').click();
    await page.locator('#draw-length').fill('4.5');
    await page.locator('#next').click(); await page.locator('#previous').click();
    assert.equal(await page.locator('#draw-length').inputValue(), '4.5');
    assert.equal(await page.locator('#draw-length').getAttribute('readonly'), null);
    assert.match(await page.locator('#screen-status').innerText(), /1 stretches/);
    await page.locator('#place').click();
    await page.locator('[data-select="side"]').click();
    await page.locator('#draw-length').fill('4.8'); await page.locator('#place').click();
    assert.match(await page.locator('#plan').textContent(), /4.8 m/);

    await step(2); await page.locator('#height').fill('2.2');
    await page.locator('#model').selectOption('Routed vinyl');
    await page.locator('[data-detail-tab="Base"]').click();
    await page.locator('#base').selectOption('Concrete');
    await page.locator('[data-detail-tab="Fence"]').click();
    await page.locator('#next').click(); await page.locator('#previous').click();
    assert.equal(await page.locator('#height').inputValue(), '2.2');
    assert.equal(await page.locator('#model').inputValue(), 'Routed vinyl');
    await page.locator('[data-detail-tab="Base"]').click();
    assert.equal(await page.locator('#base').inputValue(), 'Concrete');
    await page.locator('[data-detail-tab="Fence"]').click();
    assert.match(await page.locator('#save-state').innerText(), /unsaved/);
    await step(5); await page.locator('#preview-package').click();
    assert.match(await page.locator('#package-content').innerText(), /drafts have not been saved/);
    assert.doesNotMatch(await page.getByRole('table', { name: 'Saved specification' }).innerText(), /Routed vinyl/);
    await page.keyboard.press('Escape');
    await step(2); await page.locator('#height').fill('4'); await page.locator('#save-details').click();
    assert.match(await page.locator('#form-error').innerText(), /Enter a height/);
    await page.locator('#height').fill('2'); await page.locator('#save-details').click();
    assert.equal(await page.locator('#form-error').innerText(), '');

    await reset(); await step(3); await page.locator('#apply-range').click();
    await page.locator('#undo-range').click(); await step(2);
    await page.locator('#height').fill('2.2'); await page.locator('#save-details').click();
    await step(3);
    assert.equal(await page.locator('#plan .range-overlay').count(), 0);
    assert.match(await page.locator('#range-summary').innerText(), /Full stretch: 2.2 m/);
    await page.locator('#range-height').fill('1.4');
    assert.equal(await page.locator('#plan .range-overlay').count(), 1);
    await page.locator('#range-start').fill('9');
    assert.ok(await page.locator('#apply-range').isDisabled());

    await reset(); await step(4);
    const amberPoint = await page.locator('#plan .range-overlay line').evaluate(el => {
      const point = new DOMPoint((el.x1.baseVal.value + el.x2.baseVal.value) / 2, el.y1.baseVal.value).matrixTransform(el.getScreenCTM());
      return { x: point.x, y: point.y };
    });
    await page.mouse.click(amberPoint.x, amberPoint.y);
    assert.equal(await page.locator('#inspector h3').innerText(), 'Street fence A-B');
    await step(4); await page.locator('#gate-offset').fill('7.5');
    assert.ok(await page.locator('#save-gate').isDisabled());
    await page.locator('#gate-offset').fill('2');
    await page.locator('#gate-swing').selectOption('Outward');
    assert.equal(await page.locator('#plan [data-swing]').getAttribute('data-swing'), 'Outward');

    await reset(); await step(1); await page.locator('#draw-length').fill('4');
    await page.locator('#place').click(); await page.locator('#place').click();
    const geometry = await page.evaluate(() => ({
      house: { x: document.querySelector('#house-reference').getBBox().x, width: document.querySelector('#house-reference').getBBox().width },
      fenceX: +document.querySelector('#plan [data-run="side"] line').getAttribute('x1'),
    }));
    assert.ok(geometry.house.x + geometry.house.width < geometry.fenceX);

    await reset(); await step(4);
    for (let i = 0; i < 4; i++) await page.locator('#zoom-in').click();
    assert.equal(await page.locator('#zoom-label').innerText(), '140%');
    assert.ok(await page.locator('#plan-wrap').evaluate(el => el.scrollHeight > el.clientHeight));
    await page.locator('#plan-wrap').evaluate(el => el.scrollTo(el.scrollWidth, el.scrollHeight));
    assert.ok(await page.locator('#plan-wrap').evaluate(el => el.scrollTop > 0));
    const key = await page.locator('.canvas-key').boundingBox();
    const viewport = await page.locator('#plan-wrap').boundingBox();
    assert.ok(key.y >= viewport.y + viewport.height);
    assert.equal(await page.getByRole('group', { name: 'Plan zoom' }).count(), 1);
    await page.locator('#zoom-reset').click();
    assert.equal(await page.locator('#plan-wrap').evaluate(el => el.scrollTop), 0);

    await page.locator('[data-step="2"]').focus(); await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.step), '2');
    await page.locator('[data-select="side"]').focus(); await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.select), 'side');
    await page.locator('#plan [data-run="street"]').first().focus(); await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.run), 'street');
    await page.locator('[data-source="contract"]').click(); await page.locator('#source-open').click();
    assert.equal(await page.getByRole('dialog', { name: 'Signed contract / example' }).count(), 1);
    await page.keyboard.press('Escape');

    await reset(); await step(5); await page.locator('#preview-package').click();
    const dialog = page.getByRole('dialog', { name: 'Example handover package' });
    assert.ok(await dialog.isVisible());
    const facts = await page.getByRole('table', { name: 'Saved specification' }).innerText();
    for (const value of ['8 m', '5 m', 'Slat panel', 'Soil', '0-3 m: 1.8 m', '3-8 m: 1.4 m']) assert.ok(facts.includes(value), value);
    assert.match(await page.locator('#package-content').innerText(), /1 m opening, 2-3 m from A. Opens inward/);
    assert.equal(await page.locator('[data-package-source]').count(), 6);
    for (const source of ['contract', 'sketch', 'amendment', 'message', 'photo', 'construction']) {
      await page.locator(`[data-package-source="${source}"]`).click();
      assert.ok(await page.locator('#source-dialog').isVisible());
      if (source === 'photo') {
        await page.locator('#source-expanded img').evaluate(img => img.decode());
        assert.ok(await page.locator('#source-expanded img').evaluate(img => img.naturalWidth > 0));
        await page.screenshot({ path: path.join(output, 'photo.png') });
      }
      await page.keyboard.press('Escape');
    }
    await dialog.evaluate(el => el.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, 'package.png') });
    await page.keyboard.press('Escape');
    const ids = await page.locator('[id]').evaluateAll(els => els.map(el => el.id));
    assert.equal(new Set(ids).size, ids.length, 'Duplicate DOM IDs');
    for (const width of [1280, 1440, 1600, 1920]) {
      await page.setViewportSize({ width, height: 1000 });
      for (let i = 0; i < 6; i++) {
        await step(i);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(output, `${width}-step-${i}.png`) });
      }
    }
    assert.deepEqual(errors, []);
    console.log('PASS: review regressions, saved package, all six sources, keyboard, zoom, and six chapters at four desktop widths.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
