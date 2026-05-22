const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:3001';

function roundedBox(box) {
    return {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height)
    };
}

async function measureTabs(viewport) {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport });

    await page.goto(FRONTEND_URL, { waitUntil: 'networkidle' });
    await page.click('#schemaBtn');
    await page.waitForSelector('#schemaModal.show', { timeout: 10000 });
    await page.waitForSelector('.database-modal-content', { timeout: 10000 });

    const measurements = {};
    for (const tabName of ['explore', 'query', 'about', 'faq']) {
        await page.click(`[data-database-tab="${tabName}"]`);
        await page.waitForSelector(`[data-database-panel="${tabName}"]:not([hidden])`, { timeout: 5000 });
        await page.waitForTimeout(80);
        const box = await page.locator('.database-modal-content').boundingBox();
        measurements[tabName] = roundedBox(box);
    }

    await browser.close();
    return measurements;
}

function assertStable(measurements) {
    const base = measurements.explore;
    for (const [tabName, box] of Object.entries(measurements)) {
        assert.equal(box.width, base.width, `${tabName} changed modal width`);
        assert.equal(box.height, base.height, `${tabName} changed modal height`);
        assert.ok(Math.abs(box.x - base.x) <= 1, `${tabName} shifted modal x`);
        assert.ok(Math.abs(box.y - base.y) <= 1, `${tabName} shifted modal y`);
    }
}

(async () => {
    const desktop = await measureTabs({ width: 1440, height: 950 });
    const mobile = await measureTabs({ width: 390, height: 844 });

    assertStable(desktop);
    assertStable(mobile);

    console.log(JSON.stringify({ desktop, mobile }, null, 2));
})().catch((error) => {
    console.error(error);
    process.exit(1);
});
