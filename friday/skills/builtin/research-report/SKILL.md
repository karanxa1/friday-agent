---
name: research-report
description: Research a topic across the web and deliver a cited PDF report. Use when the user asks for research, a report, a comparison, or a write-up on any subject.
---

# Research → cited PDF report

Goal: turn a research question into a well-structured, cited PDF the user can download.

## Steps
1. **Clarify scope** only if the question is too broad to act on; otherwise proceed.
2. **Search broadly.** Use the web search / research tools with several distinct queries
   (definitions, comparisons, recent developments, criticisms). Open the most useful sources.
3. **Verify before stating.** Prefer facts you actually read in a source over recall. Note the URL
   for each key claim so you can cite it.
4. **Synthesize** into sections: Summary, Key findings, Details/Comparison (use a table when
   comparing options), Caveats, Sources (numbered list of URLs).
5. **Deliver as PDF.** Call `make_pdf` with Markdown content and a title. Surface the returned
   link to the user. Offer to adjust depth or focus.

## Quality bar
- Every non-obvious claim is traceable to a source in the Sources list.
- No fabricated figures. If you couldn't verify something, say so.
- The PDF opens and reads cleanly; tables render.
