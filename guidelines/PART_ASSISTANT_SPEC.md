\# PART ASSISTANT SPEC (AI-READY)

Scope: Part numbering + part type/policy selection + attribute checks + documentation expectations + push-to-SAP readiness.



\## A) Part numbering: format + assignment workflow

\### Standard IGT part number format

AAABBBCCD where:

\- AAA = required 3-digit family prefix

\- BBB = required 3-digit sequence

\- CC = required 2-digit suffix

\- D = optional extension



\### How to assign

\- AAA prefix: select per REF0178 (Part Family Prefix)

\- BBB sequence: next available number in that family using Part Number Search Tool (HE115)

\- Exceptions exist (example called out: single conductor wire uses a nonstandard BBB coding scheme)



\## B) Part Type selection (decision tree)

The assistant should guide Part Type selection per the HE042 decision tree.

Types include (non-exhaustive):

\- Document Part

\- Proprietary Part

\- Color

\- Tool

\- Assembly

\- Finished Part

\- Commercial Part

\- Material\_IGT

\- Unfinished Part

\- Packaging

\- SERIALIZED (only if explicitly instructed)



Material\_IGT note:

\- Material\_IGT parts use Gram UOM and are used in BOMs for Unfinished/Finished parts.



\## C) Policy selection

\- Development Part policy: Create/Peer Review/Complete; defaults to EA revision

\- EC Part policy: Preliminary/Review/Approved/Released; defaults to A revision

Rule of thumb:

\- Use Development Part when creating “revision Ex” parts.

\- Use EC Part for Production Level, Tool, Color, Document Part, Packaging, SAP Graphic parts.



\## D) Name/Description constraints

\- Part Name (part number): ALL CAPS, <= 18 chars, no disallowed characters; Autoname must remain unchecked.

\- Description: ALL CAPS, <= 40 chars, no disallowed characters; structure should follow HE015 naming principles.

\- Owner: usually creator; change if creating for another person (so they receive lifecycle notifications).



\## E) Unit of Measure (UOM) is critical

\- UOM drives SAP UOM.

\- UOM must be correct before pushing to SAP.

\- Fixing a wrong UOM generally requires Release-to-Obsolete and creating a new part number (exception: DD and EA can be interchanged by Hardware or Manufacturing Coordinator).



\## F) Documentation expectations (common patterns)

\### Commercial or Material\_IGT (when documentation exists)

Upload documents into Reference Documents container with consistent comment tags, examples:

\- DOCS (user guide / installation manual)

\- MSDS

\- SPEC

\- Quote



\### Material\_IGT additional expectation

\- Under Specifications, add existing latest released 98699900 CAD Drawing.

\- If sourcing to “IGT Qualified Vendor”: create item-specific CAD Drawing + check-in IGT Specification; otherwise optional.



\## G) Tool Part creation (special case)

When creating Tool parts in Matrix:

\- Part Type = Tool

\- Enter tool part number in Part Name

\- Tool lifecycle bypasses Development Part; defaults to EC Part with revision A

\- Environmental Compliance Required must be set to NO

\- Tool Cost and Vendor are required fields (Tool Cost is numeric only; no $ or commas)

\- Set Weight to 0.0

\- Attach vendor quotes/documents to Reference Document (and tool design file required for capitalized tools)



\## H) Push Development Parts to SAP readiness checklist

Before pushing unreleased parts to SAP:

\- Verify part attributes (Part Type, Part Name, Policy, Subsidiary Part, UOM, Basic Material, etc.)

\- Ensure part(s) are attached to an ECO

Push methods:

\- Single part: Part PowerView → Request push to SAP (route auto-starts)

\- Multiple parts: ECO PowerView → select parts → Request push to SAP (one route per part)



\## I) Deleting parts

\- If part exists in SAP: cannot delete; must be released to OB/IN.

\- If not in SAP: can delete in Enovia by searching, selecting, delete.

