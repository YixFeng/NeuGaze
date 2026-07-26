# README Left Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every explicitly aligned container in the English and Chinese READMEs render left-aligned.

**Architecture:** Preserve the existing README HTML structure and replace only the alignment attribute values. Verify exact occurrence counts and inspect a two-file-only diff.

**Tech Stack:** Markdown, embedded HTML, Git

## Global Constraints

- Modify only `README.md` and `README-CN.md`.
- Replace every `align="center"` with `align="left"`.
- Preserve all badges, video markup, tables, headings, links, and text.
- Do not change application code or other documentation.

---

### Task 1: Left-align both READMEs

**Files:**
- Modify: `README.md`
- Modify: `README-CN.md`

**Interfaces:**
- Consumes: the existing embedded HTML containers in both README files.
- Produces: the same container structure with `align="left"` attributes.

- [ ] **Step 1: Run the pre-change assertion**

```bash
python -c "from pathlib import Path; files=[Path('README.md'), Path('README-CN.md')]; counts={p.name:p.read_text().count('align=\"center\"') for p in files}; assert counts == {'README.md': 0, 'README-CN.md': 0}, counts"
```

Expected: FAIL and report four centered attributes in each README.

- [ ] **Step 2: Apply the minimal replacement**

In both files, replace exactly:

```html
align="center"
```

with:

```html
align="left"
```

Do not change any surrounding tags or content.

- [ ] **Step 3: Verify exact alignment counts**

```bash
python -c "from pathlib import Path; files=[Path('README.md'), Path('README-CN.md')]; result={p.name:(p.read_text().count('align=\"center\"'), p.read_text().count('align=\"left\"')) for p in files}; assert result == {'README.md': (0, 4), 'README-CN.md': (0, 4)}, result; print(result)"
```

Expected: PASS and print zero centered plus four left-aligned attributes per file.

- [ ] **Step 4: Verify the exact diff**

```bash
git diff --check
git diff --stat -- README.md README-CN.md
git diff -- README.md README-CN.md
git status --short
```

Expected: only eight attribute-value replacements across the two README files, with no whitespace errors.

- [ ] **Step 5: Commit**

```bash
git add README.md README-CN.md
git commit -m "docs: left-align README content"
```
