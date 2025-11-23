const fs = require("fs");
const path = require("path");
const xlsx = require("xlsx");
const puppeteer = require("puppeteer-extra");
const StealthPlugin = require("puppeteer-extra-plugin-stealth");
const UserAgent = require("user-agents");

puppeteer.use(StealthPlugin());

const HEADERS = [
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

const CONFIG = {
  maxRetries: 3,
  excelPath:
    process.argv[2] ||
    process.env.MAPS_XLSX ||
    path.resolve(__dirname, "businesses.xlsx"),
  viewport: { width: 1400, height: 900 },
  navigationTimeoutMs: 90_000
};

const wait = (min = 250, max = 600) =>
  new Promise(resolve =>
    setTimeout(resolve, Math.floor(min + Math.random() * (max - min)))
  );

const toIsoDate = label => {
  if (!label) {
    return "";
  }
  const clean = label.replace(/\u202f/g, " ").trim();
  const parsed = Date.parse(clean);
  if (!Number.isNaN(parsed)) {
    return new Date(parsed).toISOString().split("T")[0];
  }

  const relativeMatch = clean.match(/(\d+)\s+(day|week|month|year)/i);
  if (relativeMatch) {
    const value = Number(relativeMatch[1]);
    const unit = relativeMatch[2].toLowerCase();
    const now = new Date();
    const date = new Date(now);
    const multipliers = {
      day: 1,
      week: 7,
      month: 30,
      year: 365
    };
    const days = (multipliers[unit] || 0) * value;
    date.setDate(now.getDate() - days);
    return date.toISOString().split("T")[0];
  }

  return clean;
};

const runWithRetry = async (fn, retries, label) => {
  let lastError;
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      return await fn(attempt);
    } catch (error) {
      lastError = error;
      console.warn(
        `[WARN] ${label} attempt ${attempt} failed: ${error.message}`
      );
      await wait(1200, 2000);
    }
  }
  throw lastError;
};

const loadWorkbook = workbookPath => {
  if (!fs.existsSync(workbookPath)) {
    throw new Error(
      `Excel file not found at ${workbookPath}. Provide a valid path as argv[2] or MAPS_XLSX.`
    );
  }
  const workbook = xlsx.readFile(workbookPath);
  const sheetName = workbook.SheetNames[0];
  const sheet = workbook.Sheets[sheetName];
  const rows = xlsx.utils.sheet_to_json(sheet, { defval: "" });
  return { workbook, sheetName, rows };
};

const saveWorkbook = (workbook, sheetName, rows, workbookPath) => {
  const normalizedRows = rows.map(row => {
    const normalized = {};
    HEADERS.forEach(header => {
      normalized[header] =
        row[header] === undefined || row[header] === null ? "" : row[header];
    });
    return normalized;
  });
  workbook.Sheets[sheetName] = xlsx.utils.json_to_sheet(normalizedRows, {
    header: HEADERS
  });
  xlsx.writeFile(workbook, workbookPath);
};

const setFreshPagePersona = async page => {
  const ua = new UserAgent().toString();
  await page.setUserAgent(ua);
  await page.setExtraHTTPHeaders({
    "Accept-Language": "en-US,en;q=0.9"
  });
  await page.setViewport(CONFIG.viewport);
};

const dismissBanners = async page => {
  const selectors = [
    'button[aria-label*="Accept"]',
    'button[aria-label*="agree"]',
    '#introAgreeButton',
    'button[aria-label*="Agree"]',
    'button[jsname="higCR"]',
    'button[jsname="LogIjd"]'
  ];
  for (const selector of selectors) {
    const el = await page.$(selector);
    if (el) {
      await el.click().catch(() => {});
      await wait();
    }
  }
  await page.evaluate(() => {
    const keywords = ["accept all", "agree", "got it", "no thanks"];
    document
      .querySelectorAll("button")
      .forEach(btn => {
        const text = (btn.innerText || btn.textContent || "").toLowerCase();
        if (keywords.some(key => text.includes(key))) {
          btn.click();
        }
      });
  }).catch(() => {});
};

const clickTabByText = async (page, tabLabel) => {
  const clicked = await page.evaluate(label => {
    const target = (label || "").toLowerCase();
    const elements = Array.from(
      document.querySelectorAll('[role="tab"], button, a')
    );
    const node = elements.find(el => {
      const text = (el.innerText || el.textContent || "").toLowerCase();
      const aria = (el.getAttribute("aria-label") || "").toLowerCase();
      return text.includes(target) || aria.includes(target);
    });
    if (node) {
      node.click();
      return true;
    }
    return false;
  }, tabLabel);
  if (!clicked) {
    throw new Error(`Unable to find ${tabLabel} tab`);
  }
  await wait(500, 900);
};

const getAppState = async page => {
  const rawState = await page
    .evaluate(() => {
      const script = Array.from(document.scripts).find(s =>
        s.textContent.includes("APP_INITIALIZATION_STATE")
      );
      if (!script) {
        return null;
      }
      const text = script.textContent;
      const startIndex = text.indexOf("APP_INITIALIZATION_STATE");
      if (startIndex === -1) {
        return null;
      }
      const firstBracket = text.indexOf("[", startIndex);
      if (firstBracket === -1) {
        return null;
      }
      let depth = 0;
      for (let i = firstBracket; i < text.length; i += 1) {
        const char = text[i];
        if (char === "[") depth += 1;
        else if (char === "]") {
          depth -= 1;
          if (depth === 0) {
            return text.slice(firstBracket, i + 1);
          }
        }
      }
      return null;
    })
    .catch(() => null);

  if (!rawState) return null;
  try {
    return JSON.parse(rawState);
  } catch {
    return null;
  }
};

const extractPhotoFromState = state => {
  if (!state) return null;
  const stack = [state];
  const prefix = "https://lh3.googleusercontent.com/p/";
  while (stack.length) {
    const value = stack.pop();
    if (typeof value === "string" && value.startsWith(prefix)) {
      return value.split("=")[0];
    }
    if (Array.isArray(value)) {
      stack.push(...value);
    } else if (value && typeof value === "object") {
      stack.push(...Object.values(value));
    }
  }
  return null;
};

const extractPhotoFromDom = async page =>
  page
    .evaluate(() => {
      const img = document.querySelector('img[src^="https://lh3.googleusercontent.com/"]');
      return img ? img.src.split("=")[0] : null;
    })
    .catch(() => null);

const sortReviewsByNewest = async page => {
  const opened = await page
    .evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button"));
      const sortButton = buttons.find(btn => {
        const aria = (btn.getAttribute("aria-label") || "").toLowerCase();
        const text = (btn.innerText || "").toLowerCase();
        return aria.includes("sort reviews") || text.includes("sort");
      });
      if (sortButton) {
        sortButton.click();
        return true;
      }
      return false;
    })
    .catch(() => false);

  if (!opened) {
    console.warn("[WARN] Sort menu not found, continuing with default order.");
    return;
  }

  await page.waitForSelector('div[role="menu"]', { timeout: 5000 }).catch(() => {});
  await wait(200, 400);

  await page
    .evaluate(() => {
      const items = Array.from(
        document.querySelectorAll('div[role="menuitem"], span, button')
      );
      const target = items.find(el =>
        (el.innerText || "").toLowerCase().includes("newest")
      );
      if (target) {
        target.click();
      }
    })
    .catch(() => {});

  await wait(800, 1200);
};

const scrollReviews = async page => {
  await page
    .evaluate(async () => {
      const scroller = document.querySelector('div[aria-label$="Google reviews"]');
      if (!scroller) return;
      for (let i = 0; i < 3; i += 1) {
        scroller.scrollBy({ top: scroller.scrollHeight, behavior: "smooth" });
        await new Promise(res => setTimeout(res, 800));
      }
      scroller.scrollTo({ top: 0, behavior: "smooth" });
    })
    .catch(() => {});
  await wait(400, 700);
};

const extractNewestReview = async page => {
  await page.waitForSelector('div[data-review-id]', { timeout: 15_000 }).catch(() => {});
  const data = await page
    .evaluate(() => {
      const card = document.querySelector('div[data-review-id]');
      if (!card) return null;
      const textSelectors = [
        '[jsname="fbQN7e"]',
        '[jsname="P8j2ed"]',
        ".wiI7pd",
        ".MyEned"
      ];
      let textContent = "";
      for (const selector of textSelectors) {
        const node = card.querySelector(selector);
        if (node && node.innerText.trim()) {
          textContent = node.innerText.trim();
          break;
        }
      }
      const dateNode = card.querySelector(".rsqaWe") || card.querySelector("span");
      const dateText = dateNode ? dateNode.innerText.trim() : "";
      return {
        text: textContent,
        date: dateText
      };
    })
    .catch(() => null);
  if (!data) return null;
  return {
    latest_review: data.text,
    latest_review_date: toIsoDate(data.date)
  };
};

const scrapeBusiness = async (page, url, label) =>
  runWithRetry(
    async attempt => {
      await setFreshPagePersona(page);
      await page.goto("about:blank");
      await wait(200, 400);

      await page.goto(url, {
        waitUntil: "networkidle0",
        timeout: CONFIG.navigationTimeoutMs
      });
      await dismissBanners(page);
      await wait(500, 900);

      const appState = await getAppState(page);

      await clickTabByText(page, "photos");
      await page
        .waitForSelector('img[src^="https://lh3.googleusercontent.com/"]', {
          timeout: 15_000
        })
        .catch(() => {});

      const latestPhotoUrl =
        extractPhotoFromState(appState) || (await extractPhotoFromDom(page));

      await clickTabByText(page, "reviews");
      await page
        .waitForSelector('div[aria-label$="Google reviews"]', { timeout: 15_000 })
        .catch(() => {});
      await sortReviewsByNewest(page);
      await scrollReviews(page);
      const reviewData = await extractNewestReview(page);

      if (!latestPhotoUrl && !reviewData) {
        throw new Error("No photo or review data captured");
      }

      return {
        latest_photo_url: latestPhotoUrl || "",
        latest_review: reviewData?.latest_review || "",
        latest_review_date: reviewData?.latest_review_date || ""
      };
    },
    CONFIG.maxRetries,
    label
  );

const processRows = async (page, rows, workbook, sheetName, workbookPath) => {
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    HEADERS.forEach(header => {
      if (row[header] === undefined) {
        row[header] = "";
      }
    });
    const mapsUrl = (row.maps_url || "").trim();
    if (!mapsUrl) {
      console.log(`[SKIP] Row ${index + 1}: missing maps_url`);
      continue;
    }

    const label = row.name || mapsUrl;
    console.log(
      `[INFO] (${index + 1}/${rows.length}) ${label} — starting scrape`
    );

    try {
      const result = await scrapeBusiness(page, mapsUrl, label);
      if (result.latest_photo_url) row.latest_photo_url = result.latest_photo_url;
      if (result.latest_review) row.latest_review = result.latest_review;
      if (result.latest_review_date)
        row.latest_review_date = result.latest_review_date;
      console.log(
        `[INFO] (${index + 1}/${rows.length}) ${label} — success: photo ${
          row.latest_photo_url ? "✓" : "✗"
        }, review ${row.latest_review ? "✓" : "✗"}`
      );
    } catch (error) {
      console.error(
        `[ERROR] (${index + 1}/${rows.length}) ${label} — ${error.message}`
      );
    } finally {
      saveWorkbook(workbook, sheetName, rows, workbookPath);
    }
    await wait(1200, 2000);
  }
};

const main = async () => {
  const workbookPath = path.resolve(CONFIG.excelPath);
  const { workbook, sheetName, rows } = loadWorkbook(workbookPath);

  const browser = await puppeteer.launch({
    headless: false,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-blink-features=AutomationControlled"
    ],
    defaultViewport: null
  });

  try {
    const page = await browser.newPage();
    page.setDefaultNavigationTimeout(CONFIG.navigationTimeoutMs);
    page.on("dialog", dialog => dialog.dismiss().catch(() => {}));

    await processRows(page, rows, workbook, sheetName, workbookPath);
  } finally {
    await browser.close();
  }
};

main().catch(error => {
  console.error(`[FATAL] ${error.message}`);
  process.exitCode = 1;
});
