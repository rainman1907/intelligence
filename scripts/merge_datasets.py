#!/usr/bin/env python3
"""
Utility script to merge scraped Google Maps reviews/photos back into the master dataset.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

import pandas as pd


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def write_table(df: pd.DataFrame, path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df.to_csv(path, index=False)
    elif suffix in {".xlsx", ".xlsm"}:
        df.to_excel(path, index=False)
    else:
        raise ValueError(f"Unsupported output type: {suffix}")


def merge_datasets(source_path: Path, scraped_path: Path, output_path: Path) -> None:
    source_df = read_table(source_path)
    scraped_df = read_table(scraped_path)

    if "Row_ID" not in scraped_df.columns:
        raise ValueError("Scraped result is missing the Row_ID column.")

    if "Row_ID" not in source_df.columns:
        source_df = source_df.reset_index(drop=False)
        source_df["Row_ID"] = source_df["index"] + 1
        source_df = source_df.drop(columns=["index"])

    merged = pd.merge(source_df, scraped_df, on="Row_ID", how="left", validate="one_to_one")
    write_table(merged, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge scraped reviews/photos with the original dataset.")
    parser.add_argument("--source-file", required=True, help="Original master dataset (.csv or .xlsx).")
    parser.add_argument("--scraped-file", required=True, help="Scraper output file.")
    parser.add_argument("--output-file", required=True, help="Where to write the merged dataset.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    merge_datasets(Path(args.source_file), Path(args.scraped_file), Path(args.output_file))


if __name__ == "__main__":
    main()
