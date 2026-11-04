# Raw sources

Sources exactly as ingested: the text of a paper, a catalog page, a talk's notes, a data
file's description. **Never edit a file here after it is added**; all interpretation goes
in [../concepts/](../concepts/_index.md) and [../references/](../references/_index.md).

- One file per source, `<short-slug>.md`, starting with frontmatter: `title`, `source`
  (DOI, URL or "manual"), `ingested` (date), and a two or three sentence `summary`.
- `kind: text` when the file holds the source's text. If the text cannot be committed
  (license, size, a binary such as a PDF), add a pointer file instead: `kind: pointer`, a
  `pointer-reason:`, the locator, and short quotes (with their numbers) of every statement
  the project uses. A copy for reading goes in `local/`, which git ignores. The `ingest` skill has the steps; `bin/wiki-check` checks them.
- Add a row below for each file.

| file | title | ingested |
|---|---|---|
