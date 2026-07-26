# README Left Alignment Design

## Goal

Make the English and Chinese README content render left-aligned instead of
inheriting center alignment from their outer HTML containers.

## Scope

- Change every `align="center"` attribute in `README.md` and `README-CN.md`
  to `align="left"`.
- Preserve the existing HTML container structure, badges, video, tables,
  headings, links, and text.
- Do not modify other documentation or application code.

## Verification

- Assert neither README contains `align="center"`.
- Assert both READMEs contain the same number of `align="left"` attributes
  as their previous centered attributes.
- Run `git diff --check` and inspect the exact two-file diff.
