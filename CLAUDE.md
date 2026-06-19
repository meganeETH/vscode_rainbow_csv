# CLAUDE.md

Guidance for AI assistants (and humans) working in this repository.

## What this is

**Rainbow CSV** — a Visual Studio Code extension (publisher `mechatroner`, MIT license)
that highlights CSV/TSV/separated files with per-column colors and provides an SQL-like
query language (**RBQL**), column alignment, CSVLint consistency checks, hover info,
column tracking, sticky headers, and Excel/Markdown export.

The extension ships to both the **desktop** VSCode marketplace and **OpenVSX**, and runs
as a **web extension** (browser, e.g. vscode.dev). It is written in plain **JavaScript**
(CommonJS), not TypeScript.

- User-facing docs: `README.md`
- Maintainer/dev notes (read this for environment quirks): `DEV_README.md`
- Version history: `CHANGELOG.md` (current version is tracked in `package.json`)

## Repository layout

| Path | Purpose |
|------|---------|
| `extension.js` | **Main entry point** (`activate`/`deactivate`). Command registration, VSCode event handlers, decoration/semantic-token providers, RBQL orchestration, autodetection, alignment, preview, status bar. Large (~2900 lines). |
| `rainbow_utils.js` | Core pure-ish utilities: column-stat calculation, alignment/shrink, inlay hints, RFC document parsing, cursor/hover info, RBQL IO handlers (`VSCodeRecordIterator`, `VSCodeWriter`), markdown generation. Heavily unit-tested. |
| `fast_load_utils.js` | `parse_document_records` — the fast, low-level CSV record parser used for autodetection and lint. |
| `rbql_client.js` / `rbql_client.html` | Webview UI for the RBQL query console. |
| `rbql_suggest.js` | Column-name autocomplete logic inside the RBQL console webview. |
| `dialect_select.js` / `dialect_select.html` | Webview UI for the "Dynamic CSV" separator selection dialog. |
| `syntaxes/*.tmLanguage.json` | TextMate grammars, one per built-in dialect (csv, tsv, scsv, pipe, wspcsv, dynamic). |
| `rbql_core/` | **Vendored** RBQL engine — Python (`rbql/`) and JavaScript (`rbql-js/`). Upstream: github.com/mechatroner/RBQL. Treat as a dependency; do not hand-edit unless syncing from upstream. |
| `contrib/` | **Vendored** third-party libs: `wcwidth` (double-width char handling) and `textarea-caret-position`. |
| `test/` | Tests + sample CSV fixtures (`test/csv_files/`). |
| `webpack.config.js` | Web (browser/webworker) bundle config → `dist/web/`. |
| `package.json` | Manifest: contributes (languages, commands, config, colors), scripts, dev deps. |

## Key architecture concepts

- **Two runtime targets.** `package.json` declares `main: ./extension` (Node/desktop) and
  `browser: ./dist/web/extension.js` (web, built by webpack). The same `extension.js`
  source serves both. Detect the environment with `is_web_ext = (os.homedir === undefined)`.
  Functions/commands that rely on Node APIs (`fs`, `child_process`, file paths) are marked
  with a `// WEB_DISABLED` comment in the command registrations and must degrade gracefully
  in the browser.

- **Lazy loading for startup performance.** Heavy modules are required lazily via
  `ll_rbql_csv()` and `ll_rainbow_utils()` rather than at top of file. Preserve this
  pattern — startup latency is intentionally guarded (DEV_README mentions an
  `is_lazy_loaded` test check).

- **Dialects = (separator, policy).** See `dialect_map` in `extension.js`. Policies:
  `quoted` (commas/semicolons ignored inside double quotes), `simple` (tsv, pipe),
  `whitespace` (consecutive whitespace merged), `quoted_rfc` (multiline RFC-4180 fields,
  used by "Dynamic CSV"). Language ids must be lowercase: `csv`, `tsv`, `csv (semicolon)`,
  `csv (pipe)`, `csv (whitespace)`, `dynamic csv`.

- **Highlighting mechanism.** Built-in dialects use static TextMate grammars in
  `syntaxes/`. "Dynamic CSV" uses VSCode **semantic tokenization** (`RainbowTokenProvider`)
  because the separator is arbitrary/runtime-defined.

- **Persistent state.** `global_state` (VSCode `globalState`) survives restarts and stores
  things like dynamic dialect info and join-table mappings. In-memory maps live on the
  `extension_context` object near the top of `extension.js`.

- **Defensive/idempotent programming.** Per DEV_README, VSCode filetype persistence is
  unreliable; enable/disable logic may run redundantly (e.g. on both doc open and close).
  This is intentional — keep such operations idempotent rather than "fixing" the redundancy.

## Build, test, lint

All commands are npm scripts (run `npm install` first):

```bash
npm run lint            # eslint over extension.js, rainbow_utils.js, fast_load_utils.js,
                        # test/runTest.js (node config) + browser-context files (browser config)
npm run compile-web     # webpack build of the web extension into dist/web/
npm run package-web     # production webpack build (used by vscode:prepublish)
npm run unit-test-only  # pure unit tests, no VSCode needed: node test/suite/run_unit_tests.js
npm test                # full integration tests in desktop VSCode (@vscode/test-electron)
npm run test-in-browser # integration tests in headless browser (requires compile-web first)
npm run start-web-server# serve the web extension locally for manual browser debugging
```

### Testing notes

- **`test/suite/unit_tests.js`** holds the pure unit tests (`test_all()` runs them). These
  do not need a running VSCode — they use **test doubles** for the VSCode API
  (`VscodeDocumentTestDouble`, `VscodeRangeTestDouble`, `vscode_test_double`, etc.). Prefer
  adding fast unit tests here when changing logic in `rainbow_utils.js` / `fast_load_utils.js`.
- **`test/suite/index.js`** holds the VSCode integration tests (highlighting, commands,
  RBQL end-to-end), driven by `test/runTest.js` (electron) or webpack→browser.
- Many functions in `rainbow_utils.js` are exported solely so unit tests can reach them
  (comments say `// Only for unit tests.`). When adding a testable helper, export it the
  same way.
- Quirk: integration tests can fail intermittently if VSCode reopens files from a previous
  session. See DEV_README for the close-all-tabs workaround. Run integration tests with no
  other VSCode windows open.

## Conventions

- **Language/style:** plain ES (CommonJS `require`/`module.exports`), `ecmaVersion: 8`.
  `ts-loader` exists in webpack config but the source is JS. Match the surrounding
  `snake_case` naming for functions and variables (this codebase does not use camelCase for
  locals).
- **Lint rules that fail the build:** `no-trailing-spaces` (error) and `semi` always
  (error). Most other rules are warnings. Run `npm run lint` before committing.
- **Two eslint configs:** `eslint.config.mjs` (Node context, browser globals off) and
  `eslint.config_browser.mjs` (browser context for webview scripts). Webview-facing files
  (`rbql_client.js`, `dialect_select.js`, and `rainbow_utils.js` for shared bits) are linted
  under the browser config.
- **Don't edit vendored code** in `rbql_core/` or `contrib/` to make local fixes — those are
  synced from upstream. Fix in the extension layer instead, or note an upstream sync.
- **Keep `README.md`, `CHANGELOG.md`, and `package.json` `version` in sync** when shipping
  user-visible changes. New commands/config also need entries under `contributes` in
  `package.json` plus menu wiring.

## Adding a feature (typical flow)

1. New command: register in `activate()` in `extension.js` and add to `contributes.commands`
   (and `menus`/`activationEvents` as needed) in `package.json`. Mark `// WEB_DISABLED` if
   it needs Node APIs.
2. New setting: add under `contributes.configuration.properties` in `package.json` and read
   it via `get_from_config(...)`, wiring it into `extension_context` if it should be cached.
3. Put pure logic in `rainbow_utils.js` / `fast_load_utils.js`, export it, and add unit
   tests in `test/suite/unit_tests.js`.
4. Run `npm run lint` and `npm run unit-test-only`; run integration tests if behavior in
   VSCode changed.

## Releasing (maintainer reference — see DEV_README for full details)

- Desktop marketplace: `vsce publish <major|minor|patch> -p <key>` (runs the prepublish
  webpack build automatically).
- OpenVSX: `npx ovsx publish -p <token>` (uses version already in `package.json`).
- `node_modules/`, `package-lock.json`, etc. are excluded from the package via `.vscodeignore`.
- `.github/workflows/release.yml` packages a `.vsix` and uploads it to the GitHub Release on
  `release: published`.

## Pre-publish checklist (from DEV_README)

- Run unit tests in the browser target as well as desktop.
- Verify the **sticky header** feature works when enabled.
- Verify **Dynamic CSV → Dynamic CSV** separator switching works.
- Run `npm run lint`.
