#!/usr/bin/env node
"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const yargs_1 = __importDefault(require("yargs"));
const helpers_1 = require("yargs/helpers");
const logger_1 = require("./logger");
const input_1 = require("./input");
const auth_1 = require("./auth");
const maps_1 = require("./maps");
(async () => {
    const argv = await (0, yargs_1.default)((0, helpers_1.hideBin)(process.argv))
        .option('input', { type: 'string', demandOption: true, desc: 'Path to CSV/Excel with columns: map_url, website' })
        .option('headless', { type: 'boolean', default: false, desc: 'Run browser headless' })
        .option('storage-state', { type: 'string', desc: 'Path to Playwright storageState JSON to reuse Gmail login' })
        .option('cookies-txt', { type: 'string', desc: 'Path to Netscape cookies.txt (from Chrome/Extensions) for google.com' })
        .option('out', { type: 'string', default: 'results.csv', desc: 'Output CSV of results' })
        .strict()
        .help()
        .parse();
    const rows = await (0, input_1.loadRows)(argv.input);
    logger_1.logger.info({ count: rows.length }, 'Loaded rows');
    await (0, maps_1.withBrowser)(argv.headless, async (browser) => {
        const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
        await (0, auth_1.applyAuth)(context, { storageState: argv['storage-state'], cookiesTxt: argv['cookies-txt'] });
        // If no auth provided, allow manual login once
        const page = await context.newPage();
        await page.goto('https://accounts.google.com/', { waitUntil: 'domcontentloaded' });
        logger_1.logger.info('If needed, sign in to Google in the opened browser. Press Enter here when done...');
        await new Promise((resolve) => {
            process.stdin.setRawMode?.(true);
            process.stdin.resume();
            process.stdin.once('data', () => resolve());
        });
        await page.close();
        const results = [];
        results.push('map_url,website,status,message');
        for (const { map_url, website } of rows) {
            const res = await (0, maps_1.submitWebsiteEdit)(context, { mapUrl: map_url, website });
            logger_1.logger.info({ res }, 'Processed');
            results.push([map_url, website, res.status, JSON.stringify(res.message || '')].join(','));
        }
        fs_1.default.writeFileSync(path_1.default.resolve(argv.out), results.join('\n'));
        logger_1.logger.info({ out: path_1.default.resolve(argv.out) }, 'Wrote results CSV');
        // Save storage state for reuse
        const storagePath = path_1.default.resolve('auth/storageState.json');
        fs_1.default.mkdirSync(path_1.default.dirname(storagePath), { recursive: true });
        await context.storageState({ path: storagePath });
        logger_1.logger.info({ storagePath }, 'Saved storage state');
        await context.close();
    });
})();
