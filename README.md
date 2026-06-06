# Relief Docket

<p align="center">
  <img src="data_files/logo_transparent.png" alt="Relief Docket logo" width="280">
</p>

Relief Docket is an interactive public dashboard about the United States immigration court system.

It is built to answer plain-language questions like:

- Which immigration courts have the largest caseloads?
- How different are asylum grant rates from one judge to another?
- Which nationalities appear most often in immigration court data?
- How often are cases decided when someone is not present in court?
- How do policy changes show up in court outcomes over time?

The goal is not to tell anyone what should happen in a particular case. The goal is to make a very large public dataset easier to understand.

## What Data This Uses

The main source is the EOIR CASE database, published by the Executive Office for Immigration Review through its public FOIA library.

EOIR is the part of the U.S. Department of Justice that runs immigration courts. Its CASE database contains millions of records about immigration court cases, proceedings, applications, hearing locations, judges, decisions, and related lookup tables.

This repository currently includes small, pre-built data files in `data/` so the app can load quickly without downloading the full EOIR release. Those files were generated from a local June 2026 EOIR release.

Current real-data status:

- Last EOIR release loaded: `2026-06`
- Cases: `12,552,603`
- Proceedings: `16,376,510`
- Applications: `15,921,543`
- Seed mode: `false`

That means the dashboard is using real EOIR pipeline output, not sample data.

## What Is Real Right Now

These sections currently use real EOIR-derived data:

- Judges
- Courts
- Nationalities and countries of origin
- Case outcomes
- Attorney representation gap
- Policy trend metrics
- In absentia orders
- In absentia rates by court
- A derived annual backlog timeline
- BIA appeals
- Federal court appeal records
- Bond analytics
- EOIR custody and detention-history metrics
- Removal pathway breakdowns
- Juvenile-history / unaccompanied-children metrics
- Case age and backlog age distributions

Some measures have limits because EOIR does not publish every field people might expect. For example, the EOIR federal appeal table does not identify the circuit, and true ICE detention bed counts require ICE or DHS detention data. The app keeps those limits visible rather than filling gaps with made-up numbers.

## Why Some Data May Look Imperfect

Public immigration court data is powerful, but it is not clean in the way people expect a spreadsheet to be clean.

Known issues include:

- EOIR changes table formats over time.
- Some records can disappear from later monthly releases.
- Codes can change meaning across years.
- Some case types are not included in the same way as others.
- A raw grant rate does not always control for case type, nationality, attorney representation, detention status, or local docket practices.

Relief Docket keeps a canonical database that is designed not to delete old records when EOIR omits them from a later release. The app also includes a Data Quality page so readers can see what the data can and cannot support.

## Technical Details

For setup instructions, rebuild commands, repository layout, and pipeline notes, see [Technical Notes](docs/technical.md). For a more detailed list of what was implemented and what EOIR still cannot prove by itself, see [Real Data Roadmap](docs/real_data_roadmap.md).

## Picking Up The Work

For a future coding assistant or contributor, start here:

- [Repo Summary](docs/repo_summary.md) explains the app structure, data files, and important commands.
- [Next Model Handoff](docs/model_handoff_2026-06-05.md) records the current working state, verification already run, and what to watch next.
- [Pipeline Diagram](docs/pipeline_diagram.md) shows the EOIR data flow as a Mermaid chart.
- [Data Enhancement Roadmap](docs/data_enhancement_roadmap.md) ranks future bronze/silver-backed data additions by priority and difficulty.

## A Plain-English Caution

This project can show patterns. It cannot explain every cause behind those patterns.

For example, two judges may have different grant rates because of differences in case mix, nationality mix, attorney representation, detained versus non-detained dockets, time period, or many other factors. A number on this site should be treated as a starting point for investigation, not as a final judgment about a person, court, or case.

## Status

The current build is ready to run with real EOIR-derived data from the June 2026 CASE release.
