# Pipeline Diagram

[Back to README](../README.md)

This Mermaid diagram shows the current EOIR data flow from local download to the deployed Streamlit app.

```mermaid
flowchart TD
    A[EOIR FOIA CASE release<br/>June 2026 / 2026-06] --> B[scripts/download.py]
    B --> C[bronze/<br/>raw ZIPs and extracted CSV/TSV files<br/>ignored by Git]

    C --> D[scripts/ingest.py]
    D --> E[silver/2026-06.core2.duckdb<br/>raw EOIR tables in DuckDB<br/>ignored by Git]

    E --> F[scripts/canonical.py]
    F --> G[silver/canonical.roadmap3.duckdb<br/>normalized canonical tables<br/>ignored by Git]

    G --> H[scripts/aggregate.py]
    H --> I[data/*.parquet and data/*.json<br/>small app-ready files<br/>committed to Git]

    I --> J[utils/data_loader.py]
    J --> K[cases.py and pages/*.py<br/>Streamlit dashboard]

    subgraph Core EOIR Tables
        T1[A_TblCase]
        T2[B_TblProceeding]
        T3[E_TblApplication]
        T4[tblLookupHloc / Judge / CourtDecision / Nationality]
    end

    subgraph Extended Dashboard Tables
        X1[D_TblAssociatedBond]
        X2[tbl_CustodyHistory]
        X3[tbl_JuvenileHistory]
        X4[tblAppeal / tblAppealFedCourts / tblThreeMbrReferrals]
        X5[tbl_schedule]
        X6[B_TblProceedCharges]
        X7[tbl_RepsAssigned / tbl_EOIR_Attorney]
        X8[tbl_Court_Motions]
    end

    T1 --> D
    T2 --> D
    T3 --> D
    T4 --> D
    X1 --> D
    X2 --> D
    X3 --> D
    X4 --> D
    X5 --> D
    X6 --> D
    X7 --> D
    X8 --> D

    subgraph Roadmap Gold Outputs
        R1[annual judge/court/nationality trends]
        R2[representation and attorney aggregates]
        R3[case age, bond, custody, schedule, continuance]
        R4[appeal, charge, motion, quality, release snapshot]
    end

    H --> R1
    H --> R2
    H --> R3
    H --> R4
    R1 --> I
    R2 --> I
    R3 --> I
    R4 --> I

    subgraph Git Boundary
        C
        E
        G
        I
    end

    C -. ignored .-> E
    E -. ignored .-> G
    I -. committed .-> K
```

## Short Version

- `bronze/` is raw EOIR data and stays local.
- `silver/` is DuckDB build output and stays local.
- `data/` is the small generated app data and is committed.
- Streamlit reads only `data/` at runtime, so deploys are fast.
