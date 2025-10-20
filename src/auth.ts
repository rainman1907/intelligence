import fs from 'fs';
import path from 'path';
import { BrowserContext } from 'playwright';
import { logger } from './logger';

export interface CookieFormat {
  // Playwright storage state JSON path
  storageState?: string;
  // Netscape cookies.txt path
  cookiesTxt?: string;
}

export async function applyAuth(context: BrowserContext, cookies: CookieFormat): Promise<void> {
  if (cookies.storageState) {
    try {
      const storageStatePath = path.resolve(cookies.storageState);
      const storageState = JSON.parse(fs.readFileSync(storageStatePath, 'utf-8'));
      await context.addCookies(storageState.cookies || []);
      logger.info({ storageStatePath }, 'Applied cookies from storageState');
      return;
    } catch (err) {
      logger.warn({ err }, 'Failed to apply storageState cookies');
    }
  }
  if (cookies.cookiesTxt) {
    try {
      const cookiesTxtPath = path.resolve(cookies.cookiesTxt);
      const cookiesList = parseNetscapeCookies(fs.readFileSync(cookiesTxtPath, 'utf-8'));
      await context.addCookies(cookiesList);
      logger.info({ cookiesTxtPath }, 'Applied cookies from cookies.txt');
      return;
    } catch (err) {
      logger.warn({ err }, 'Failed to apply cookies.txt cookies');
    }
  }
}

function parseNetscapeCookies(content: string): any[] {
  const lines = content.split(/\r?\n/);
  const cookies: any[] = [];
  for (const line of lines) {
    if (!line || line.startsWith('#')) continue;
    const parts = line.split('\t');
    if (parts.length < 7) continue;
    const [domain, , pathVal, secureFlag, expiry, name, value] = parts;
    cookies.push({
      name,
      value,
      domain,
      path: pathVal,
      expires: Number(expiry) || undefined,
      httpOnly: false,
      secure: secureFlag.toUpperCase() === 'TRUE',
      sameSite: 'Lax',
    });
  }
  return cookies;
}
