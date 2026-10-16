# Part Number Search Tool Reverse Engineering and Integration

## Executive summary

The supplied macro workbook is a SAP Analysis for Office client for BW query `ZENG_V01_Q001` (`Eng: Part Number Query (Direct Access)`). It does two separate jobs:

1. SAP AO retrieves material number, source system, and description rows from SAP ECC, Matrix, and Mapics for a prompted material range.
2. VBA reduces every returned material number to its first six digits (`AAA+BBB`) and lists gaps in that six-digit sequence.

The workbook does **not** determine the correct `AAA` family. Per the engineering guideline pack, that mapping comes from REF0178. The app therefore keeps family selection separate from sequence allocation.

## Workbook behavior recovered

- SAP AO revision: `2.8.1800.0560`.
- SAP data provider: `DS_1`.
- BW query: `ZENG_V01_Q001`.
- Query name: `Eng: Part Number Query (Direct Access)`.
- SAP variables shown by the workbook: `ZVCP_MATDA` and `ZVCP_MSSYS`.
- Source filter: `ZSOURCE1 = ALL`.
- Returned columns: Material, Source of Data, Material Description.
- Workbook sources observed: Matrix, SAP ECC, and Mapics.
- Cached refresh timestamp: May 23, 2025 at 01:14:13.
- Cached range: `629 - 630`, displayed as `629000 - 630000` after macro normalization.
- Cached data: 3,352 source rows, 1,385 distinct eight-digit materials in family 629.
- Cached result: occupied six-digit sequences through `629979`; the next candidate sequence is `629980`, which becomes `62998000` with suffix `00`.

The Refresh button runs `Source_Refresh`. It connects to SAP if necessary, opens the AO prompt screen, refreshes the query, then calls `Sheet1Macro`. That macro calculates `LEFT(material, 6)` for each result and loops from the selected lower bound to upper bound, using `COUNTIF` to emit missing values.

## Risks and defects in the workbook implementation

- The upper bound `630000` belongs to the next family but is emitted as unused. The app limits family 629 to `629000..629999`.
- The VBA numeric validation does not correctly require both range endpoints to be numeric.
- A gap is only a point-in-time observation. The workbook has no reservation, transaction, or final revalidation, so two engineers can select the same number.
- Cached workbook data is not safe evidence for a production create. The attached snapshot was last refreshed in 2025.
- The algorithm intentionally treats any suffix in a six-digit sequence as occupying the entire `AAA+BBB` sequence. That matches `AAABBBCCD`, where `CC` is a suffix under the allocated sequence.
- The workbook depends on a Windows desktop SAP AO add-in and should not be automated from the RHEL web server.

## Implemented application flow

The app now exposes `workflow.part_number.plan`:

1. Interpret the request and select a configured family.
2. Read occupied sequences from Matrix and SAP/legacy sources.
3. Normalize valid part numbers to their first six digits.
4. Select the first unused value inside the family only.
5. Apply a two-digit suffix (default `00`).
6. Return a creation summary with family evidence, candidate, alternatives, attributes, BOM items, findings, and staged Matrix actions.

The UI's **New Part Number** tab accepts a natural-language request such as “Let's pull a P/N for a new Bracket...”, optional family override, suffix, part type, UOM, and BOM rows. It stages one `matrix.part.create` action and one `matrix.bom.add_item` action per BOM row.

Family `629 = Bracket` is included as a provisional fallback inferred from the workbook. It remains visibly unverified until a controlled REF0178 mapping is installed.

## SAP connector modes

- `mock` (default): deterministic demo data; never authorizes a production create.
- `workbook-snapshot`: set `SAP_PART_SEARCH_WORKBOOK` to an `.xlsm` path. The app reads the cached SAP/Mapics/Matrix crosstab without Excel or SAP AO. It is useful for validation and migration, but candidates remain blocked pending live revalidation.
- `unavailable`: returned when the configured snapshot cannot be read.

Example for local validation:

```powershell
$env:SAP_PART_SEARCH_WORKBOOK = "C:\path\to\Engineering - Part Number Search Tool.xlsm"
.\scripts\dev.cmd
```

For production, implement a server-side SAP adapter for query `ZENG_V01_Q001` or an approved ABAP/OData/RFC wrapper. The minimal contract is:

- Input: material-family range and source selection `ALL`.
- Output: material number, source system, and material description.
- Required safety: service authentication, timeouts, audit correlation, explicit freshness, and an exact pre-create recheck.

## Remaining production work

1. Obtain REF0178 and install a reviewed `config/part_number_families.local.json` with `verified: true` mappings.
2. Choose and implement the supported SAP server interface. The workbook contains system/query metadata but no reusable web-service credentials.
3. Add a durable allocation/reservation table with a uniqueness constraint on `AAA+BBB`, expiry, actor, and workflow ID.
4. Add an exact live SAP + Matrix recheck in the same transaction immediately before creation.
5. Connect `matrix.part.create` and `matrix.bom.add_item` to approved Matrix write APIs. The supplied Postman catalog exposes read-capable MQL but no approved part/BOM write endpoint.
6. Replace the prototype approval service's “mock-executed” status transition with real connector execution, idempotency keys, compensation/error states, and audit evidence.
7. Confirm which Matrix attributes and relationships are mandatory for each Part Type, including ECO attachment and push-to-SAP readiness rules.

Until items 1–6 are complete, the summary page is an auditable planning/staging surface, not a production number allocator.
