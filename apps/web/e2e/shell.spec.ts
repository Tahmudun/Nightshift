import { expect, test } from '@playwright/test';

/**
 * These run with no API behind them, on purpose. Every assertion here is about
 * the app being honest about what it cannot reach.
 */

test('the root redirects to Explore', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/explore$/);
  await expect(page.getByRole('heading', { name: 'Explore', level: 1 })).toBeVisible();
});

test('all three modes are reachable and mark themselves current', async ({ page }) => {
  await page.goto('/explore');

  for (const mode of ['Operate', 'Analyze', 'Explore']) {
    await page.getByRole('navigation', { name: 'Modes' }).getByRole('link', { name: mode }).click();
    await expect(page.getByRole('heading', { name: mode, level: 1 })).toBeVisible();
    await expect(
      page.getByRole('navigation', { name: 'Modes' }).getByRole('link', { name: mode }),
    ).toHaveAttribute('aria-current', 'page');
  }
});

test('a missing API is reported, not hidden', async ({ page }) => {
  await page.goto('/explore');
  // The telemetry strip must say so rather than showing an ambiguous blank.
  await expect(page.getByText('api unreachable')).toBeVisible();
  // And the list must explain the failure instead of rendering an empty state,
  // which would falsely imply the database is empty.
  await expect(page.getByText('Could not load roles')).toBeVisible();
});

test('the confidence legend documents all five levels without an API', async ({ page }) => {
  await page.goto('/explore');
  for (const label of ['Verified', 'Approximate', 'City only', 'Remote', 'Unknown']) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }
});

test('the skip link is the first thing keyboard focus reaches', async ({ page }) => {
  await page.goto('/explore');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
});
