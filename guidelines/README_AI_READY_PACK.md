\# IGT AI-READY ECO + PART ASSISTANT PACK

Version: 0.1 (draft for implementation)

Scope: Enovia/Matrix ECO creation/workflow + Part creation/standards + Title/Drafting compliance checks.



\## 1. Purpose

This pack is intended for AI-assisted applications that:

\- Help users CREATE ECOs and Parts in Enovia/Matrix correctly

\- INSPECT existing ECOs/Parts for compliance issues

\- SUGGEST corrections in a consistent, auditable way



This pack does NOT replace governing procedures. It is a structured layer that maps

checks → recommended actions → source procedures.



\## 2. Operating model (recommended)

\### 2.1 Deterministic validators first (fast, consistent)

Run rule checks (regex/field checks/state gates) before using an LLM.



\### 2.2 LLM second (explanations + suggestions)

Use the LLM to:

\- explain why a rule fired

\- propose compliant alternative text (titles/descriptions)

\- propose next actions (e.g., “set VC Notes Required to Yes/No”)

Always cite the governing procedure section (via your RAG retrieval).



\### 2.3 “No invention” policy

If the needed detail is not found in the governing docs, the assistant must say so and

request the minimum missing info.



\## 3. Inputs expected by the assistant

\- ECO object: basic attributes + lifecycle state + attached ECRs + tabs (New Parts, Revised Parts, etc.)

\- Part object: part number, type, policy, description, UOM, basic material, compliance fields, ECO-to-release, etc.

\- Document object (drawing/spec): title, number, revision, and whether it matches Matrix title/description.



\## 4. Outputs expected by the assistant

Return a structured response:

\- PASS/FAIL per gate (Create, Promote-to-Review, Release-to-SAP, etc.)

\- Findings list with severity (BLOCKER/ERROR/WARN/INFO)

\- Suggested fixes (auto-fixable text + user-confirm-required)

\- References (doc IDs/sections; your system should turn these into citations)



\## 5. Suggested gating points

\- ECO Create State (before Promote)

\- ECO Promote to Review (VC Notes + Coordinator Instructions set)

\- ECO Define Components (tabs populated, ECR attached where required)

\- ECO Release (conflict report + SAP transfer)

\- Part Create (name/type/policy/UOM/description/disallowed characters)

\- Part Push-to-SAP (attributes correct, attached to ECO)

\- Title/Drafting checks (HE015 + MAN-HE01 alignments)



\## 6. Files in this pack

\- ECO\_ASSISTANT\_SPEC.md

\- PART\_ASSISTANT\_SPEC.md

\- TITLE\_DRAFTING\_SPEC.md

\- RULE\_CATALOG.yaml

\- SCHEMAS.json

