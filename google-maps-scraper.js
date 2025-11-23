#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const xlsx = require("xlsx");
const UserAgent = require("user-agents");
const puppeteer = require("puppeteer-extra");
const StealthPlugin = require("puppeteer-extra-plugin-stealth");

puppeteer.use(StealthPlugin());

const DEFAULT_HEADERS = [
  "name",
  "address",
  "maps_url",
  "phone",
  "website",
  "category",
  "rating",
  "review_count",
  "latest_review",
  "latest_review_date",
  "latest_photo_url"
];

const MAX_RETRIES = 3;
const NAVIGATION_TIMEOUT = 120000;
const DEFAULT_FILE = "maps-input.xlsx";

(async function main() {
  try {
    const inputPath = resolveInputPath();
    const workbookState = loadWorkbook(inputPath);
    if (!workbookState.rows.length) {
      console.warn("No data rows detected in the Excel file.");
      return;
    }

    console.log(
      `Processing ${workbookState.rows.length} rows from ${workbookState.filePath}`
    );

    const browser = await puppeteer.launch({
      headless: false,
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled"
      ]
    });

    try {
      for (let index = 0; index < workbookState.rows.length; index += 1) {
        const row = workbookState.rows[index];
        const url = (row.maps_url || "").trim();
        const label = row.name || row.address || `Row ${index + 2}`;

        if (!url) {
          console.warn(
            `[${index + 1}/${workbookState.rows.length}] Missing maps_url for "${label}", skipping.`
          );
          continue;
        }

        const success = await processBusiness(browser, row, index + 1, workbookState.rows.length, url, label);
        persistWorkbook(workbookState, inputPath);

        if (!success) {
          console.error(
            `[${index + 1}/${workbookState.rows.length}] Failed after ${MAX_RETRIES} attempts for "${label}".`
          );
        }
      }
    } finally {
      await browser.close();
    }

    persistWorkbook(workbookState, inputPath);
    console.log("Scraping completed. Excel file updated.");
  } catch (error) {
    console.error("Fatal error:", error);
    process.exitCode = 1;
  }
})();

function resolveInputPath() {
  const provided = process.argv[2];
  const resolved = path.resolve(process.cwd(), provided || DEFAULT_FILE);
  if (!fs.existsSync(resolved)) {
    throw new Error(
      `Input Excel file not found at ${resolved}. Pass the file path as the first argument.`
    );
  }
  return resolved;
}

function loadWorkbook(filePath) {
  const workbook = xlsx.readFile(filePath);
  const sheetName = workbook.SheetNames[0];
  if (!sheetName) {
    throw new Error("Workbook does not contain any sheets.");
  }

  const worksheet = workbook.Sheets[sheetName];
  const headerRows = xlsx.utils.sheet_to_json(worksheet, { header: 1 });
  const headerOrder =
    (headerRows && headerRows.length && headerRows[0].length
      ? headerRows[0]
      : [...DEFAULT_HEADERS]);

  DEFAULT_HEADERS.forEach((col) => {
    if (!headerOrder.includes(col)) headerOrder.push(col);
  });

  const rows = xlsx.utils.sheet_to_json(worksheet, { defval: "" });

  return { workbook, sheetName, headerOrder, rows, filePath };
}

function persistWorkbook(workbookState, outputPath) {
  const normalizedRows = workbookState.rows.map((row) => {
    const normalized = {};
    workbookState.headerOrder.forEach((key) => {
      normalized[key] = row[key] ?? "";
    });
    return normalized;
  });

  const updatedSheet = xlsx.utils.json_to_sheet(normalizedRows, {
    header: workbookState.headerOrder,
    skipHeader: false
  });

  workbookState.workbook.Sheets[workbookState.sheetName] = updatedSheet;
  xlsx.writeFile(workbookState.workbook, outputPath);
}

async function processBusiness(browser, row, index, total, url, label) {
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt += 1) {
    let page;
    try {
      page = await browser.newPage();
      await configurePage(page);

      console.log(
        `[${index}/${total}] (${attempt}/${MAX_RETRIES}) Loading ${url} (${label})`
      );
      await page.goto(url, {
        waitUntil: "networkidle2",
        timeout: NAVIGATION_TIMEOUT
      });
      await randomDelay(900, 1600);

      await dismissCookieBanners(page);
      await waitForInitializationState(page);

      await clickPrimaryTab(page, "photos");
      await waitForPhotos(page);
      await randomDelay();

      const photoFromState = await extractPhotoFromState(page);
      const photoFromDom = photoFromState || (await extractPhotoFromDom(page));
      if (photoFromDom) {
        row.latest_photo_url = photoFromDom;
      } else {
        console.warn(`[${index}/${total}] Could not locate a photo URL for "${label}".`);
      }

      await randomDelay(800, 1500);

      await clickPrimaryTab(page, "reviews");
      await waitForReviews(page);
      await sortReviewsByNewest(page);
      await randomDelay(600, 1200);
      await slowScroll(page, 4, 480);

      const reviewDetails = await extractLatestReviewFromDom(page);
      if (reviewDetails && reviewDetails.text) {
        row.latest_review = reviewDetails.text;
        const reviewTimestamp =
          reviewDetails.timestamp ||
          (await extractTimestampFromState(page, reviewDetails.text));
        const resolvedDate =
          reviewDetails.isoDate ||
          (reviewTimestamp ? formatDateFromTimestamp(reviewTimestamp) : null) ||
          normalizeRelativeDate(reviewDetails.relativeDate);

        if (resolvedDate) {
          row.latest_review_date = resolvedDate;
        }
      } else {
        console.warn(
          `[${index}/${total}] Review details missing for "${label}".`
        );
      }

      console.log(`[${index}/${total}] Done: ${label}`);
      await page.close();
      return true;
    } catch (error) {
      if (page && !page.isClosed()) {
        await page.close().catch(() => {});
      }
      console.error(
        `[${index}/${total}] Attempt ${attempt} failed for "${label}": ${error.message}`
      );
      await randomDelay(1500, 3000);
    }
  }
  return false;
}

async function configurePage(page) {
  const userAgent = new UserAgent();
  await page.setUserAgent(userAgent.toString());
  await page.setViewport({
    width: randomInt(1280, 1600),
    height: randomInt(720, 950)
  });
  await page.setJavaScriptEnabled(true);
  await page.setExtraHTTPHeaders({
    "Accept-Language": "en-US,en;q=0.9"
  });
  page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT);
  page.setDefaultTimeout(60000);
}

async function dismissCookieBanners(page) {
  const buttonTexts = [
    "accept all",
    "agree",
    "accept",
    "i agree",
    "got it",
    "allow"
  ];

  const clickByText = async (ctx) => {
    return ctx.evaluate((targets) => {
      const elements = Array.from(
        document.querySelectorAll('button, div[role="button"]')
      );
      for (const el of elements) {
        const label = `${(el.innerText || "").trim()} ${(el.getAttribute("aria-label") || "").trim()}`.toLowerCase();
        if (targets.some((target) => label.includes(target))) {
          el.click();
          return true;
        }
      }
      return false;
    }, targetsLower(buttonTexts));
  };

  const knownSelectors = [
    'button[aria-label="Accept all"]',
    '#introAgreeButton',
    'button[aria-label="I agree"]'
  ];

  for (const selector of knownSelectors) {
    const handle = await page.$(selector);
    if (handle) {
      await handle.click().catch(() => {});
      await randomDelay(500, 900);
      return true;
    }
  }

  if (await clickByText(page)) {
    await randomDelay(500, 900);
    return true;
  }

  for (const frame of page.frames()) {
    try {
      if (!frame.url().includes("consent.google")) continue;
      if (await clickByText(frame)) {
        await randomDelay(500, 900);
        return true;
      }
    } catch (_) {
      // Ignore frame access issues
    }
  }
  return false;
}

async function clickPrimaryTab(page, label) {
  const target = label.toLowerCase();
  const clicked = await page.evaluate((text) => {
    const selectors = ["[role='tab']", "button", "a"];
    for (const selector of selectors) {
      const elements = Array.from(document.querySelectorAll(selector));
      for (const el of elements) {
        const combined = `${(el.innerText || "").trim()} ${(el.getAttribute("aria-label") || "").trim()}`.toLowerCase();
        if (combined.includes(text)) {
          el.click();
          return true;
        }
      }
    }
    return false;
  }, target);

  if (!clicked) {
    throw new Error(`Unable to find the "${label}" tab.`);
  }
}

async function waitForPhotos(page) {
  await page.waitForFunction(
    () => document.querySelectorAll("img[src*='lh3.googleusercontent.com/p/']").length > 0,
    { timeout: 20000 }
  );
}

async function waitForReviews(page) {
  await page.waitForFunction(
    () =>
      document.querySelector("div[data-review-id]") ||
      document.querySelector(".jftiEf"),
    { timeout: 25000 }
  );
}

async function waitForInitializationState(page) {
  await page
    .waitForFunction(
      () =>
        Boolean(window.APP_INITIALIZATION_STATE || window.__APP_INITIALIZATION_STATE__),
      { timeout: 15000 }
    )
    .catch(() => {});
}

async function sortReviewsByNewest(page) {
  const opened = await page.evaluate(() => {
    const buttons = Array.from(
      document.querySelectorAll("button, div[role='button']")
    );
    const target = buttons.find((el) => {
      const label = `${(el.innerText || "").trim()} ${(el.getAttribute("aria-label") || "").trim()}`.toLowerCase();
      return label.includes("sort");
    });
    if (target) {
      target.click();
      return true;
    }
    return false;
  });

  if (!opened) {
    console.warn("Sort button not found; continuing without explicitly sorting.");
    return;
  }

  await page.waitForSelector("[role='menu']", { timeout: 6000 }).catch(() => {});

  const clicked = await page.evaluate(() => {
    const items = Array.from(
      document.querySelectorAll("[role='menuitem'], .VfPpkd-rymPhb")
    );
    for (const el of items) {
      const text = (el.innerText || "").trim().toLowerCase();
      if (text.includes("newest")) {
        el.click();
        return true;
      }
    }
    return false;
  });

  if (!clicked) {
    console.warn('Could not select "Newest" sort option.');
  }
}

async function slowScroll(page, steps = 4, distance = 400) {
  for (let i = 0; i < steps; i += 1) {
    await page.evaluate((scrollDistance) => {
      const scrollTarget =
        document.querySelector('[role="feed"]') ||
        document.querySelector('[aria-label*="Reviews"]') ||
        document.scrollingElement ||
        document.body;
      if (!scrollTarget) return;

      if (
        scrollTarget === document.body ||
        scrollTarget === document.documentElement ||
        scrollTarget === document.scrollingElement
      ) {
        window.scrollBy(0, scrollDistance);
      } else {
        scrollTarget.scrollTop += scrollDistance;
      }
    }, distance);
    await randomDelay(400, 800);
  }
}

async function extractPhotoFromState(page) {
  return page.evaluate(() => {
    const state =
      window.APP_INITIALIZATION_STATE || window.__APP_INITIALIZATION_STATE__;
    if (!state) return null;

    const stack = [state];
    const visited = new Set();

    while (stack.length) {
      const node = stack.pop();
      if (!node) continue;

      if (typeof node === "string" && node.startsWith("https://lh3.googleusercontent.com/p/")) {
        const clean = node.split("=")[0];
        return clean;
      }

      if (typeof node === "object") {
        if (visited.has(node)) continue;
        visited.add(node);
      }

      if (Array.isArray(node)) {
        for (const item of node) stack.push(item);
      } else if (node && typeof node === "object") {
        for (const value of Object.values(node)) stack.push(value);
      }
    }
    return null;
  });
}

async function extractPhotoFromDom(page) {
  const handle = await page.$("img[src*='lh3.googleusercontent.com/p/']");
  if (!handle) return null;
  const src = await page.evaluate((img) => img.getAttribute("src"), handle);
  await handle.dispose();
  return normalizePhotoUrl(src);
}

async function extractLatestReviewFromDom(page) {
  return page.evaluate(() => {
    const selectors = ["div[data-review-id]", ".jftiEf"];
    let card = null;
    for (const selector of selectors) {
      const candidate = document.querySelector(selector);
      if (candidate) {
        card = candidate;
        break;
      }
    }
    if (!card) return null;

    const textEl = card.querySelector(".wiI7pd");
    const text = textEl ? textEl.innerText.trim() : "";

    const relativeDate =
      card.querySelector(".rsqaWe")?.innerText?.trim() || "";
    const isoDate =
      card.querySelector('meta[itemprop="datePublished"]')?.getAttribute("content") ||
      "";
    const ratingLabel =
      card.querySelector(".kvMYJc")?.getAttribute("aria-label") || "";
    const ratingMatches = ratingLabel.match(/([\d.]+)/);
    const rating = ratingMatches ? Number(ratingMatches[1]) : null;

    const timestampAttr =
      card.getAttribute("data-review-timestamp") ||
      card.getAttribute("data-review-created-time") ||
      "";
    const timestamp = timestampAttr ? Number(timestampAttr) : null;

    return {
      text,
      relativeDate,
      isoDate,
      rating,
      timestamp: timestamp && !Number.isNaN(timestamp) ? timestamp : null
    };
  });
}

async function extractTimestampFromState(page, reviewText) {
  if (!reviewText) return null;
  return page.evaluate((text) => {
    const state =
      window.APP_INITIALIZATION_STATE || window.__APP_INITIALIZATION_STATE__;
    if (!state) return null;
    const normalizedTarget = text.trim();
    if (!normalizedTarget) return null;

    const stack = [state];
    const visited = new Set();

    const isTimestamp = (value) =>
      typeof value === "number" && value > 100000000 && value < 9999999999999;

    const findNearestTimestamp = (node) => {
      const queue = [node];
      const localVisited = new Set();

      while (queue.length) {
        const current = queue.pop();
        if (!current) continue;
        if (typeof current === "object") {
          if (localVisited.has(current)) continue;
          localVisited.add(current);
        }
        if (isTimestamp(current)) return current;
        if (Array.isArray(current)) {
          for (const child of current) queue.push(child);
        } else if (current && typeof current === "object") {
          for (const value of Object.values(current)) queue.push(value);
        }
      }
      return null;
    };

    while (stack.length) {
      const node = stack.pop();
      if (!node) continue;
      if (typeof node === "object") {
        if (visited.has(node)) continue;
        visited.add(node);
      }

      if (Array.isArray(node)) {
        const hasReviewText = node.some((fragment) => {
          if (typeof fragment !== "string") return false;
          const trimmed = fragment.trim();
          return (
            trimmed === normalizedTarget ||
            (normalizedTarget.length > 20 && trimmed.includes(normalizedTarget))
          );
        });

        if (hasReviewText) {
          const timestamp = findNearestTimestamp(node);
          if (timestamp) return timestamp;
        }

        for (const child of node) stack.push(child);
      } else if (node && typeof node === "object") {
        for (const value of Object.values(node)) stack.push(value);
      }
    }
    return null;
  }, reviewText);
}

function normalizePhotoUrl(url) {
  if (!url) return "";
  const decoded = url
    .replace(/\\u003d/g, "=")
    .replace(/\\u0026/g, "&")
    .replace(/\\\\/g, "\\");
  const base = decoded.split("=")[0];
  return base;
}

function formatDateFromTimestamp(timestamp) {
  if (!timestamp) return "";
  const ms = timestamp > 100000000000 ? timestamp : timestamp * 1000;
  return new Date(ms).toISOString().split("T")[0];
}

function normalizeRelativeDate(label) {
  if (!label) return "";
  const trimmed = label.trim();
  if (!trimmed) return "";

  const parsed = Date.parse(trimmed);
  if (!Number.isNaN(parsed)) {
    return new Date(parsed).toISOString().split("T")[0];
  }

  const lower = trimmed.toLowerCase();
  const now = new Date();

  if (lower === "today") {
    return now.toISOString().split("T")[0];
  }
  if (lower === "yesterday") {
    now.setDate(now.getDate() - 1);
    return now.toISOString().split("T")[0];
  }

  const relMatch = lower.match(/(about\s+)?(a|an|\d+)\s+(minute|hour|day|week|month|year)s?\s+ago/);
  if (relMatch) {
    const value = relMatch[2] === "a" || relMatch[2] === "an" ? 1 : Number(relMatch[2]);
    const unit = relMatch[3];
    switch (unit) {
      case "minute":
        now.setMinutes(now.getMinutes() - value);
        break;
      case "hour":
        now.setHours(now.getHours() - value);
        break;
      case "day":
        now.setDate(now.getDate() - value);
        break;
      case "week":
        now.setDate(now.getDate() - value * 7);
        break;
      case "month":
        now.setMonth(now.getMonth() - value);
        break;
      case "year":
        now.setFullYear(now.getFullYear() - value);
        break;
      default:
        break;
    }
    return now.toISOString().split("T")[0];
  }

  return "";
}

async function randomDelay(min = 500, max = 1200) {
  const duration = randomInt(min, max);
  return new Promise((resolve) => setTimeout(resolve, duration));
}

function randomInt(min, max) {
  const lower = Math.ceil(min);
  const upper = Math.floor(max);
  return Math.floor(Math.random() * (upper - lower + 1)) + lower;
}

function targetsLower(values) {
  return values.map((value) => value.toLowerCase());
}
