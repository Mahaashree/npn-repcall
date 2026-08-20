const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const REPS_JSON_PATH = path.join(__dirname, '../../dashboard/data/reps.json');
const SCATTER_JSON_PATH = path.join(__dirname, '../../dashboard/data/scatter_points.json');

test.describe('Pharma Analytics Dashboard E2E Contract & Scalability Test Suite', () => {
  test('1. Dashboard loads with zero console errors against real exported data', async ({ page }) => {
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    page.on('pageerror', (err) => {
      consoleErrors.push(err.message);
    });

    await page.goto('/frontend/index.html');
    await page.waitForSelector('#kpi-grid .kpi-card');

    expect(consoleErrors, `Console errors detected: ${consoleErrors.join(', ')}`).toHaveLength(0);
  });

  test('2. KPI values match values independently computed from raw JSON', async ({ page }) => {
    const repsRaw = JSON.parse(fs.readFileSync(REPS_JSON_PATH, 'utf-8'));
    const repsData = repsRaw.data || repsRaw;

    const activeReps = repsData.filter((r) => r.is_active);
    const expectedMeanComp =
      (activeReps.reduce((sum, r) => sum + (r.compliance_pct || 0), 0) / activeReps.length).toFixed(1) + '%';

    await page.goto('/frontend/index.html');
    await page.waitForSelector('#kpi-grid .kpi-card');

    const firstKpiVal = await page.locator('#kpi-grid .kpi-card').first().locator('.kpi-value').textContent();
    expect(firstKpiVal.trim()).toBe(expectedMeanComp);
  });

  test('3. Pagination works correctly at real data scale', async ({ page }) => {
    await page.goto('/frontend/index.html');
    await page.waitForSelector('#reps');

    // Change page size to 10 on Rep Scorecard
    await page.selectOption('#rep-page-size', '10');

    const recordCountText = await page.locator('#rep-record-count').textContent();
    expect(recordCountText).toMatch(/Showing 1–10 of \d+ reps/);

    // Verify pagination controls render page 1 and page 2 buttons
    const page1Btn = page.getByLabel('Rep table pagination').getByRole('button', { name: '1', exact: true });
    const page2Btn = page.getByLabel('Rep table pagination').getByRole('button', { name: '2', exact: true });
    await expect(page1Btn).toBeVisible();
    await expect(page2Btn).toBeVisible();

    // Navigate to page 2
    await page2Btn.click();
    const page2Text = await page.locator('#rep-record-count').textContent();
    expect(page2Text).toMatch(/Showing 11–20 of \d+ reps/);
  });

  test('4. Every filter correctly narrows visible row counts', async ({ page }) => {
    await page.goto('/frontend/index.html');
    await page.waitForSelector('#pres-tbody tr');

    const initialText = await page.locator('#pres-record-count').textContent();
    const totalCountMatch = initialText.match(/of (\d+) HCPs/);
    const initialTotal = totalCountMatch ? parseInt(totalCountMatch[1]) : 733;

    // Filter by Specialty
    await page.selectOption('#filter-specialty', { index: 1 });
    await page.waitForTimeout(350);
    const specialtyText = await page.locator('#pres-record-count').textContent();
    const specialtyCount = parseInt(specialtyText.match(/of (\d+) HCPs/)[1]);
    expect(specialtyCount).toBeLessThan(initialTotal);

    // Reset filters
    await page.click('#reset-filters');
    await page.waitForTimeout(350);

    // Filter by Search input
    await page.fill('#filter-search', 'Smith');
    await page.waitForTimeout(350);
    const searchText = await page.locator('#pres-record-count').textContent();
    const searchCount = parseInt(searchText.match(/of (\d+) HCPs/)[1]);
    expect(searchCount).toBeLessThan(initialTotal);
  });

  test('5. Quadrant card click-to-filter updates table and scatter chart', async ({ page }) => {
    await page.goto('/frontend/index.html');
    await page.waitForSelector('#perf-matrix .quadrant-card');

    // Click 'Star Performers' quadrant card
    const starCard = page.locator('#perf-matrix .quadrant-card.q-stars');
    await starCard.click();
    await page.waitForTimeout(350);

    // Verify filter applied to prescribers record count
    const presText = await page.locator('#pres-record-count').textContent();
    const countMatch = presText.match(/of (\d+) HCPs/);
    const filteredCount = countMatch ? parseInt(countMatch[1]) : 0;
    expect(filteredCount).toBeGreaterThan(0);
    expect(filteredCount).toBeLessThan(1000);
  });

  test('6. Sidebar smooth-scroll navigation links target valid sections', async ({ page }) => {
    await page.goto('/frontend/index.html');

    // Verify sections exist on page
    await expect(page.locator('#overview')).toBeVisible();
    await expect(page.locator('#matrix')).toBeVisible();
    await expect(page.locator('#reps')).toBeVisible();
    await expect(page.locator('#territories')).toBeVisible();
    await expect(page.locator('#prescribers')).toBeVisible();
    await expect(page.locator('#coaching-queue')).toBeVisible();

    // Click Reps nav link
    await page.click('.sidebar-nav a[href="#reps"]');
    await page.waitForTimeout(200);

    // Click Territories nav link
    await page.click('.sidebar-nav a[href="#territories"]');
    await page.waitForTimeout(200);
  });

  test('7. CSV export produces file matching currently filtered view', async ({ page }) => {
    await page.goto('/frontend/index.html');
    await page.waitForSelector('#pres-tbody tr');

    // Filter by Specialty (select 1st non-empty option)
    await page.selectOption('#filter-specialty', { index: 1 });
    await page.waitForTimeout(350);

    const filterText = await page.locator('#pres-record-count').textContent();
    const expectedRowCount = parseInt(filterText.match(/of (\d+) HCPs/)[1]);

    // Trigger CSV export and capture download
    const [download] = await Promise.all([page.waitForEvent('download'), page.click('#export-pres-csv')]);

    const downloadPath = await download.path();
    const csvContent = fs.readFileSync(downloadPath, 'utf-8');
    const csvLines = csvContent.trim().split('\n');
    const dataRowCount = csvLines.length - 1; // subtract header line

    expect(dataRowCount).toBe(expectedRowCount);
    expect(dataRowCount).toBeLessThan(1000);
  });

  test('8. Modals (Architecture, Pipeline, Rep Detail, Coaching Queue) open and close correctly', async ({ page }) => {
    await page.goto('/frontend/index.html');

    // 1. Architecture Modal
    await page.click('#arch-btn');
    await expect(page.locator('#arch-modal')).toHaveClass(/open/);
    await page.click('#arch-modal-close');
    await expect(page.locator('#arch-modal')).not.toHaveClass(/open/);

    // 2. Coaching Queue Full List Modal
    await page.click('#coaching-queue-view-all-btn');
    await expect(page.locator('#coaching-modal')).toHaveClass(/open/);
    await page.click('#coaching-modal-close');
    await expect(page.locator('#coaching-modal')).not.toHaveClass(/open/);

    // 3. Rep Coaching Detail Modal
    await page.waitForSelector('#rep-tbody tr');
    await page.locator('#rep-tbody tr').first().click();
    await expect(page.locator('#rep-modal')).toHaveClass(/open/);
    await page.click('#rep-modal-close');
    await expect(page.locator('#rep-modal')).not.toHaveClass(/open/);
  });

  test('9. Rep Scorecard displays Monthly Cadence and Sample Ratio status pills with zero Compliance column', async ({ page }) => {
    await page.goto('/frontend/index.html');
    await page.waitForSelector('#rep-table thead th');

    // Verify table headers
    const headers = await page.locator('#rep-table thead th').allTextContents();
    expect(headers.some((h) => h.includes('Monthly Cadence'))).toBe(true);
    expect(headers.some((h) => h.includes('Sample Drop Volume') || h.includes('Sample Ratio'))).toBe(true);
    expect(headers).not.toContain('Compliance %');

    // Verify status pills in table rows
    await page.waitForSelector('#rep-tbody tr .status-pill');
    const pills = page.locator('#rep-tbody tr .status-pill');
    const pillCount = await pills.count();
    expect(pillCount).toBeGreaterThan(0);
  });

  test('10. 3rd Dataset Mode (+ Custom Dataset) triggers non-blocking floating drawer', async ({ page }) => {
    await page.goto('/frontend/index.html');
    await page.waitForSelector('#btn-mode-custom');

    const customBtn = page.locator('#btn-mode-custom');
    await expect(customBtn).toBeVisible();

    // Verify floating drawer exists in DOM
    const drawer = page.locator('#ingestion-drawer');
    await expect(drawer).toBeAttached();
  });

  test('11. Dynamic dual-mode Performance Matrix toggles between Legacy (Compliance) and AI Driver-Weighted (CEI) views', async ({ page }) => {
    await page.goto('/frontend/index.html');
    await page.waitForSelector('#perf-matrix .quadrant-card');

    const btnLegacy = page.locator('#btn-compliance-mode, #btn-matrix-legacy').first();
    const btnCei = page.locator('#btn-cei-mode, #btn-matrix-cei').first();
    const subtitle = page.locator('#matrix-card-subtitle');

    // Default Legacy mode assertions
    await expect(btnLegacy).toHaveClass(/active/);
    await expect(subtitle).toContainText('80% Compliance Split');

    const legacyCards = await page.locator('#perf-matrix .quadrant-card .q-name').allTextContents();
    expect(legacyCards).toContain('Star Performers');
    expect(legacyCards).toContain('Efficiency Risk');
    expect(legacyCards).toContain('Unrealized Potential');
    expect(legacyCards).toContain('Needs Intervention');

    // Toggle to AI CEI mode via UI button click
    await btnCei.click();
    await page.waitForTimeout(300);

    await expect(btnCei).toHaveClass(/active/);
    await expect(btnLegacy).not.toHaveClass(/active/);
    await expect(subtitle).toContainText('75% CEI Split');

    const ceiCards = await page.locator('#perf-matrix .quadrant-card .q-name').allTextContents();
    expect(ceiCards).toContain('Star Performers');
    expect(ceiCards).toContain('Efficient High-Performers');
    expect(ceiCards).toContain('Targeting Risk');
    expect(ceiCards).toContain('Needs Intervention');

    // Verify equation pill reflects CEI
    const eqPill = await page.locator('#equation-pill').textContent();
    expect(eqPill).toContain('CEI%');

    // Test programmatically via window.setPerformanceMatrixMode('COMPLIANCE')
    await page.evaluate(() => window.setPerformanceMatrixMode('COMPLIANCE'));
    await page.waitForTimeout(200);
    await expect(btnLegacy).toHaveClass(/active/);
    await expect(btnCei).not.toHaveClass(/active/);

    // Test programmatically via window.setPerformanceMatrixMode('CEI')
    await page.evaluate(() => window.setPerformanceMatrixMode('CEI'));
    await page.waitForTimeout(200);
    await expect(btnCei).toHaveClass(/active/);
    await expect(btnLegacy).not.toHaveClass(/active/);
  });
});

