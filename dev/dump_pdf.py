"""Dev helper: download today's PDF and dump pdfplumber's view of it.

Usage: uv run python dev/dump_pdf.py
Prints, per page: the raw text, and the tables pdfplumber detects with the
default (line-based) strategy. Use this to decide the parser strategy.
"""

import pdfplumber

from hospitals.fetcher import download_pdf, fetch_listing, find_today_pdf, now_athens


def main() -> None:
    found = find_today_pdf(fetch_listing(), now_athens())
    if not found:
        print("No PDF found for today")
        return
    pdf_path = download_pdf(found[0])
    print(f"PDF: {pdf_path}  (date link: {found[1]})")
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages):
            print(f"\n===== PAGE {index} TEXT =====")
            print(page.extract_text())
            print(f"\n===== PAGE {index} TABLES (line strategy) =====")
            for table in page.extract_tables():
                for row in table:
                    print(row)
    pdf_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
