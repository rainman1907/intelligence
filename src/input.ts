import fs from 'fs';
import path from 'path';
import { parse } from 'csv-parse';
import * as XLSX from 'xlsx';

export interface Row {
  map_url: string;
  website: string;
}

export async function loadRows(inputPath: string): Promise<Row[]> {
  const ext = path.extname(inputPath).toLowerCase();
  if (ext === '.csv') {
    return await loadCsv(inputPath);
  }
  if (ext === '.xlsx' || ext === '.xls') {
    return loadExcel(inputPath);
  }
  throw new Error(`Unsupported file extension: ${ext}. Use .csv or .xlsx/.xls`);
}

async function loadCsv(filePath: string): Promise<Row[]> {
  return new Promise((resolve, reject) => {
    const rows: Row[] = [];
    fs.createReadStream(filePath)
      .pipe(parse({ columns: true, trim: true }))
      .on('data', (record: any) => {
        const map_url = (record.map_url || record["map url"] || record.url || '').toString().trim();
        const website = (record.website || record.site || '').toString().trim();
        if (map_url && website) rows.push({ map_url, website });
      })
      .on('end', () => resolve(rows))
      .on('error', reject);
  });
}

function loadExcel(filePath: string): Row[] {
  const wb = XLSX.readFile(filePath);
  const firstSheet = wb.SheetNames[0];
  const ws = wb.Sheets[firstSheet];
  const json = XLSX.utils.sheet_to_json(ws, { defval: '' }) as any[];
  const rows: Row[] = [];
  for (const record of json) {
    const map_url = (record.map_url || record["map url"] || record.url || '').toString().trim();
    const website = (record.website || record.site || '').toString().trim();
    if (map_url && website) rows.push({ map_url, website });
  }
  return rows;
}
