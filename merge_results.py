#!/usr/bin/env python3
"""
Utility script to merge the scraped reviews/photos with the original dataset.
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
from typing import Dict, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge scraped Google Maps reviews/photos with the source dataset."
    )
    parser.add_argument("--input", required=True, help="Path to the original CSV dataset.")
    parser.add_argument("--scraped", required=True, help="Path to result_reviews_photos.csv.")
    parser.add_argument(
        "--output",
        default="merged_dataset.csv",
        help="Path for the merged CSV output.",
    )
    parser.add_argument(
        "--id-column",
        default=None,
        help="Column name that uniquely identifies each record. Defaults to input row index.",
    )
    return parser.parse_args()


def load_scraped(scraped_path: Path) -> Dict[str, Dict[str, str]]:
    with scraped_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "Row_ID" not in reader.fieldnames:
            raise KeyError("Scraped file is missing the 'Row_ID' column.")
        scraped_data = {row["Row_ID"]: row for row in reader}
    logging.info("Loaded %s scraped rows.", len(scraped_data))
    return scraped_data


def merge_datasets(
    input_path: Path, scraped_path: Path, output_path: Path, id_column: str | None
) -> None:
    scraped = load_scraped(scraped_path)
    with input_path.open("r", encoding="utf-8") as input_handle, output_path.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        reader = csv.DictReader(input_handle)
        base_header: List[str] = reader.fieldnames or []
        scraped_header: List[str] = []
        if scraped:
            scraped_header = [
                col for col in next(iter(scraped.values())).keys() if col != "Row_ID"
            ]

        header = base_header + [col for col in scraped_header if col not in base_header]
        writer = csv.DictWriter(output_handle, fieldnames=header)
        writer.writeheader()

        merged_count = 0
        for idx, row in enumerate(reader, start=1):
            row_id = (
                row.get(id_column).strip()
                if id_column and row.get(id_column)
                else str(idx)
            )
            enriched = scraped.get(row_id)
            if enriched:
                for key, value in enriched.items():
                    if key == "Row_ID":
                        continue
                    row[key] = value
                merged_count += 1
            writer.writerow(row)

    logging.info(
        "Merge complete. %s records enriched out of %s total.",
        merged_count,
        idx if 'idx' in locals() else 0,
    )


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    input_path = Path(args.input).expanduser().resolve()
    scraped_path = Path(args.scraped).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input dataset not found: {input_path}")
    if not scraped_path.exists():
        raise FileNotFoundError(f"Scraped CSV not found: {scraped_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merge_datasets(input_path, scraped_path, output_path, args.id_column)


if __name__ == "__main__":
    main()
