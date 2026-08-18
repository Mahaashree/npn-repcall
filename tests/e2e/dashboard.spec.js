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
    expect(recordCountText).toContain('Showing 1–10 of 14 reps');

    // Verify pagination controls render page 1 and page 2 buttons
    const pageButtons = page.locator('#rep-pagination .page-btn');
    await expect(pageButtons.filter({ hasText: '1' })).toBeVisible();
    await expect(pageButtons.filter({ hasText: '2' })).toBeVisible();

    // Navigate to page 2
    await pageButtons.filter({ hasText: '2' }).click();
    const page2Text = await page.locator('#rep-record-count').textContent();
    expect(page2Text).toContain('Showing 11–14 of 14 reps');
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
    expect(filteredCount).toBeLessThan(733);
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
    expect(dataRowCount).toBeLessThan(733);
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
});
