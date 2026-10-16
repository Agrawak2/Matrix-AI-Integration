\# ECO ASSISTANT SPEC (AI-READY)

Scope: ECO creation + key workflow checkpoints (Create → Define Components → Review → Release-to-SAP)



\## A) ECO data model (minimum required fields)

At Create State (must exist before Promote):

\- Type (default ECO)

\- Policy (default ECO)

\- Description

\- ECO Category

\- ECO Release Code

\- Responsible Design Engineer (RDE)

\- Coordinator

\- HPS

\- Lead

\- Manager

\- SAP Project WBS

\- SAP Project Network

\- Due Date

\- Design Responsibility (default IGT)

Other fields are optional/role-dependent (Electrical Designer, Harness Designer, Mechanical Designer, Director, etc.)



\## B) ECO Release Code rules (enforce)

\- ECO-MNB: L-GTK integration (ECR requirement varies per procedure table)

\- EDU-CP: Revised Parts/Specs only; no New; no Obsolete; limited part types

\- EDU-GEN: Revised Parts/Specs only; no New (except Tool); no Obsolete; limited part types

\- NPI: New Parts/Specs only; cannot touch previously released parts; cannot attach to an ECR; cannot replace existing VC products causing trapped inventory

\- Standard: can include New + Revised + Obsolete

\- Systems: undefined (treat as “requires human confirmation”)



\## C) Required “notes” fields before Promote-to-Review

\- VC Notes Required must be explicitly set to Yes or No (not Unknown)

\- Coordinator Instructions must be set (blank is not acceptable). If none needed, set "NO INSTRUCTIONS NEEDED".



\## D) Define Components state (structure expectations)

When populating ECO content:

1\) Attach Related ECR(s) when applicable

2\) Populate:

&#x20;  - Revised Parts (as needed)

&#x20;  - Revised Specs (as needed)

&#x20;  - OB/IN Parts (as needed; disposition accuracy required)

&#x20;  - New Parts (as needed)

&#x20;  - New Specs (as needed)

3\) When all are added, RDE starts the Define Component route.



\## E) Release state → Push to SAP (Coordinator workflow checkpoint)

At ECO Release:

\- Run ECO Conflicting Parts Report (HE007) and resolve discrepancies

\- Promote ECO to Release state (Board route Approve)

\- In MxSAP Actions:

&#x20; - Create SAP ECO

&#x20; - Transfer to SAP from ECO (clear red errors; confirm black success)

&#x20; - Verify Enovia vs SAP: CC03 (ECO/revision), MM03 (OB status, revision/ECO)

&#x20; - Perform required Mass Replace steps (if applicable)

&#x20; - Mark ECO Released

\- Notify distribution list per procedure (email link from Matrix)



\## F) Assistant behaviors (what to suggest)

\- If a mandatory field is missing → BLOCKER with specific field list.

\- If Release Code conflicts with attached content:

&#x20; - NPI + attached ECR → BLOCKER

&#x20; - NPI + revised/obsoleted content → BLOCKER

&#x20; - EDU-CP/EDU-GEN + New Parts/Specs present (outside allowed exceptions) → ERROR/BLOCKER depending on gate.

\- If VC Notes Required is Unknown or Coordinator Instructions blank at Promote-to-Review gate → BLOCKER.

\- If disallowed characters exist in Description → BLOCKER (promotion risk).

\- If Systems release code → WARN + prompt for owner confirmation.

