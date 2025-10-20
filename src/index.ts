#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { chromium } from 'playwright';
import yargs from 'yargs';
import { hideBin } from 'yargs/helpers';
import { logger } from './logger';
import { loadRows } from './input';
import { applyAuth } from './auth';
import { withBrowser, submitWebsiteEdit } from './maps';

(async () => {
  const argv = await yargs(hideBin(process.argv))
    .option('input', { type: 'string', demandOption: true, desc: 'Path to CSV/Excel with columns: map_url, website' })
    .option('headless', { type: 'boolean', default: false, desc: 'Run browser headless' })
    .option('storage-state', { type: 'string', desc: 'Path to Playwright storageState JSON to reuse Gmail login' })
    .option('cookies-txt', { type: 'string', desc: 'Path to Netscape cookies.txt (from Chrome/Extensions) for google.com' })
    .option('out', { type: 'string', default: 'results.csv', desc: 'Output CSV of results' })
    .strict()
    .help()
    .parse();

  const rows = await loadRows(argv.input);
  logger.info({ count: rows.length }, 'Loaded rows');

  await withBrowser(argv.headless, async (browser) => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await applyAuth(context, { storageState: argv['storage-state'], cookiesTxt: argv['cookies-txt'] });

    // If no auth provided, allow manual login once
    const page = await context.newPage();
    await page.goto('https://accounts.google.com/', { waitUntil: 'domcontentloaded' });
    logger.info('If needed, sign in to Google in the opened browser. Press Enter here when done...');

    await new Promise<void>((resolve) => {
      process.stdin.setRawMode?.(true);
      process.stdin.resume();
      process.stdin.once('data', () => resolve());
    });
    await page.close();

    const results: string[] = [];
    results.push('map_url,website,status,message');

    for (const { map_url, website } of rows) {
      const res = await submitWebsiteEdit(context, { mapUrl: map_url, website });
      logger.info({ res }, 'Processed');
      results.push([map_url, website, res.status, JSON.stringify(res.message || '')].join(','));
    }

    fs.writeFileSync(path.resolve(argv.out), results.join('\n'));
    logger.info({ out: path.resolve(argv.out) }, 'Wrote results CSV');

    // Save storage state for reuse
    const storagePath = path.resolve('auth/storageState.json');
    fs.mkdirSync(path.dirname(storagePath), { recursive: true });
    await context.storageState({ path: storagePath });
    logger.info({ storagePath }, 'Saved storage state');

    await context.close();
  });
})();
