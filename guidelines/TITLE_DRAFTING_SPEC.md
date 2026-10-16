\# TITLE + DRAFTING COMPLIANCE SPEC (AI-READY)

Scope: HE015 title rules + core drafting checks that an AI can validate from metadata/text.



\## A) HE015 Drawing/Document Title rules (enforce)

\- Uppercase letters shall be used.

\- Do not use the words "OR" or "FOR".

\- Do not use parenthetical words/phrases in titles (e.g., "(WELDMENT)", "(MACHINED)").

\- Title must be brief but complete; use a noun name + modifiers to distinguish similar items.

\- Noun phrase should describe what the item IS / usage, not material or fabrication method.

\- If using words like ASSEMBLY / SCHEMATIC / DOCUMENT etc, they should appear as the last word and may be abbreviated if space is limited.



\## B) Practical title/description linting rules (recommended)

\- No double spaces

\- Prefer comma-separated modifier structure consistent with HE015 examples

\- Keep within system length limits (Matrix descriptions commonly limited to 40 chars)

\- Use approved abbreviations list where applicable (maintain a controlled abbreviation map)



\## C) Drafting checks from MAN-HE01 (high-value, AI-checkable)

\- Title block completeness on drawings:

&#x20; - Sheet numbering (X of X)

&#x20; - Scale present

&#x20; - Drawn/Checked/Approved fields populated per required state (especially at final release)

\- Parts List / BOM callouts:

&#x20; - IGT part numbers shall NOT be listed in drawing Parts List; use Bubble BOM item numbers that correspond to Matrix Find Numbers.

&#x20; - If vendor part number is used in Parts List, vendor name/address must be specified in general notes with delta reference.

\- Assembly drawings:

&#x20; - Bubble BOM numbers correspond to Find Numbers (F/N) from the parent Matrix BOM.



\## D) Alignment checks (common integration)

\- Drawing title in title block should match the Matrix object title/description.

\- Drawing number should match the Matrix drawing/spec number.

\- Revision displayed should match Matrix revision level.

