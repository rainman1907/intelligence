"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.applyAuth = applyAuth;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const logger_1 = require("./logger");
async function applyAuth(context, cookies) {
    if (cookies.storageState) {
        try {
            const storageStatePath = path_1.default.resolve(cookies.storageState);
            const storageState = JSON.parse(fs_1.default.readFileSync(storageStatePath, 'utf-8'));
            await context.addCookies(storageState.cookies || []);
            logger_1.logger.info({ storageStatePath }, 'Applied cookies from storageState');
            return;
        }
        catch (err) {
            logger_1.logger.warn({ err }, 'Failed to apply storageState cookies');
        }
    }
    if (cookies.cookiesTxt) {
        try {
            const cookiesTxtPath = path_1.default.resolve(cookies.cookiesTxt);
            const cookiesList = parseNetscapeCookies(fs_1.default.readFileSync(cookiesTxtPath, 'utf-8'));
            await context.addCookies(cookiesList);
            logger_1.logger.info({ cookiesTxtPath }, 'Applied cookies from cookies.txt');
            return;
        }
        catch (err) {
            logger_1.logger.warn({ err }, 'Failed to apply cookies.txt cookies');
        }
    }
}
function parseNetscapeCookies(content) {
    const lines = content.split(/\r?\n/);
    const cookies = [];
    for (const line of lines) {
        if (!line || line.startsWith('#'))
            continue;
        const parts = line.split('\t');
        if (parts.length < 7)
            continue;
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
