---
name: data-analysis
description: Analyze a dataset (CSV/Excel/JSON) and deliver charts and a summary. Use when the user uploads or points to data and wants analysis, charts, or a spreadsheet.
---

# Data analysis → charts + summary

Goal: take a dataset and return clear findings, charts, and (optionally) a cleaned spreadsheet.

## Steps
1. **Locate the data.** Uploaded files are under `uploads/`. List/read it with the files tools.
2. **Explore with run_python** using pandas: shape, dtypes, missing values, basic stats. Print what
   you find so the user sees it.
3. **Chart with matplotlib** (Agg backend — `import matplotlib; matplotlib.use("Agg")`). Save PNGs
   in the current directory; run_python returns them as links. Pick chart types that fit the
   question (trend → line, comparison → bar, distribution → histogram).
4. **Spreadsheet (optional).** Use openpyxl/pandas to write a cleaned or summarized `.xlsx`; it's
   returned as a link.
5. **Summarize** the key findings in plain language and surface every chart/file link.

## Quality bar
- Numbers come from the actual data via code you ran — never estimated.
- Charts are labeled (title, axes) and readable.
- Every generated file link is surfaced to the user.
