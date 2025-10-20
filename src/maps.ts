import { Browser, BrowserContext, chromium, Page } from 'playwright';
import { logger } from './logger';

export interface EditInput {
  mapUrl: string;
  website: string;
}

export interface EditResult {
  mapUrl: string;
  website: string;
  status: 'submitted' | 'skipped' | 'failed';
  message?: string;
}

export async function withBrowser<T>(headless: boolean, fn: (browser: Browser) => Promise<T>): Promise<T> {
  const browser = await chromium.launch({ headless });
  try {
    return await fn(browser);
  } finally {
    await browser.close();
  }
}

export async function submitWebsiteEdit(context: BrowserContext, input: EditInput): Promise<EditResult> {
  const page = await context.newPage();
  try {
    logger.info({ url: input.mapUrl }, 'Opening Maps URL');
    await page.goto(input.mapUrl, { waitUntil: 'domcontentloaded', timeout: 120_000 });

    // Wait for the place page to load by a common selector
    await page.waitForSelector('[data-value="placepage"]', { timeout: 30_000 }).catch(() => {});

    // Click "Suggest an edit"
    const suggestSelectors = [
      'button[aria-label="Suggest an edit"]',
      'button[aria-label*="Suggest an edit"]',
      'div[role="button"][aria-label*="Suggest an edit"]',
      'text=Suggest an edit',
    ];

    let clicked = false;
    for (const sel of suggestSelectors) {
      const el = await page.$(sel);
      if (el) {
        await el.click();
        clicked = true;
        break;
      }
    }
    if (!clicked) {
      // Try via keyboard shortcut or fallback
      await page.keyboard.press('KeyE').catch(() => {});
    }

    // Wait for edit dialog/panel
    await page.waitForTimeout(1000);

    // Click "Add website" or similar
    const addWebsiteSelectors = [
      'text=Add website',
      'button:has-text("Add website")',
      '[role="button"]:has-text("Add website")',
      '[aria-label*="Add website"]',
      'text=Website',
    ];

    let addClicked = false;
    for (const sel of addWebsiteSelectors) {
      const el = await page.$(sel);
      if (el) {
        await el.click();
        addClicked = true;
        break;
      }
    }

    // Find website input
    const inputSelectors = [
      'input[type="url"]',
      'input[aria-label*="Website"]',
      'input[name*="website"]',
      'input',
    ];
    let inputEl = null;
    for (const sel of inputSelectors) {
      inputEl = await page.$(sel);
      if (inputEl) break;
    }

    if (!inputEl) {
      return { mapUrl: input.mapUrl, website: input.website, status: 'failed', message: 'Website field not found' };
    }

    await inputEl.fill('');
    await inputEl.type(input.website, { delay: 20 });

    // Click Send/Submit
    const sendSelectors = [
      'button:has-text("Send")',
      'button:has-text("Submit")',
      '[role="button"]:has-text("Send")',
      '[role="button"]:has-text("Submit")',
    ];

    let submitted = false;
    for (const sel of sendSelectors) {
      const el = await page.$(sel);
      if (el) {
        await el.click();
        submitted = true;
        break;
      }
    }

    if (!submitted) {
      await page.keyboard.press('Enter').catch(() => {});
    }

    await page.waitForTimeout(1500);

    // Rudimentary success detection
    const toast = await page.$('text=Thanks for your feedback').catch(() => null);
    if (toast) {
      return { mapUrl: input.mapUrl, website: input.website, status: 'submitted' };
    }

    return { mapUrl: input.mapUrl, website: input.website, status: 'submitted', message: 'Submitted (no toast detected)' };
  } catch (err: any) {
    return { mapUrl: input.mapUrl, website: input.website, status: 'failed', message: err?.message || String(err) };
  } finally {
    await page.close();
  }
}
