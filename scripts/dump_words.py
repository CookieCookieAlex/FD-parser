"""Debug helper: dump pdfplumber's word-level extraction for inspection.

Usage: .venv/bin/python scripts/dump_words.py <pdf> <page_number_1indexed>
"""
import sys

import pdfplumber

path, page_no = sys.argv[1], int(sys.argv[2])

with pdfplumber.open(path) as pdf:
    page = pdf.pages[page_no - 1]
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        print(f"x0={w['x0']:6.1f} x1={w['x1']:6.1f} top={w['top']:6.1f} bottom={w['bottom']:6.1f}  {w['text']!r}")
