# Matrix Local Config

Local Matrix credentials and MQL templates live in `*.local.json` files in this folder. Those files are ignored by Git.

Use the setup helper to create the ignored local config files from the REST ticket notes:

```powershell
.\scripts\setup-matrix-rest-config.cmd
```

It writes:

- `config/matrix_profiles.local.json`
- `config/matrix_mql_templates.local.json`

Then run a live read-only part search:

```powershell
.\scripts\test-matrix-rest-config.cmd PCB
```

The Django Part Search tab can also call Matrix by selecting `Matrix server`.

Leave `MATRIX_CONNECTOR_MODE` unset to keep normal workflows on mock Matrix data. Set it to `rest-read` only when you want the default backend connector to use Matrix for all read-capable flows:

```powershell
$env:MATRIX_CONNECTOR_MODE = "rest-read"
```

## Part-number family and SAP snapshot config

Copy `part_number_families.example.json` to the ignored file `part_number_families.local.json`, replace the provisional mappings with the reviewed REF0178 catalog, and set `verified` to `true` only after review. Override the location with `PART_NUMBER_FAMILIES_PATH` when needed.

For migration/testing, the app can read cached results from the supplied SAP Analysis for Office workbook without launching Excel:

```powershell
$env:SAP_PART_SEARCH_WORKBOOK = "C:\path\to\part-number-search.xlsm"
```

Workbook mode is a stale snapshot and intentionally blocks production creation pending a live SAP recheck. See `docs/PART_NUMBER_INTEGRATION.md` for the recovered SAP query contract and production gaps.
