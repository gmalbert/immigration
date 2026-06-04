# Immigration Courts: A Deep Dive Into Available Data
### Research memo for legal analytics site development
*Prepared June 2026*

---

## Executive Summary

U.S. immigration court data is one of the richest, most underutilized public legal datasets in the country. The primary source — the EOIR CASE database — contains **over 164 million rows across 97 tables**, covering every immigration court proceeding since the 1970s. It is updated monthly, freely available under FOIA, and encompass individual-level records with enough granularity to support judge-by-judge analytics, nationality-level outcome tracking, detention pattern analysis, and much more. The audience — attorneys, journalists, researchers, policy advocates, and affected communities — is enormous and actively hungry for accessible analysis tools.

This memo covers what data exists, how far back it goes, how detailed it is, how frequently it updates, known data quality issues, and specific feature and data modeling recommendations for a public analytics site.

---

## The Court System Being Tracked

The Executive Office for Immigration Review (EOIR), formally established on January 9, 1983, operates under the U.S. Department of Justice and administers the nation's immigration court system. The system has three primary adjudicatory bodies:

**Immigration Courts (ICs)** — trial-level administrative courts where immigration judges (IJs) conduct removal proceedings and decide whether individuals may remain in the United States or must be removed. There are currently over 70 immigration courts nationwide.

**Board of Immigration Appeals (BIA)** — the highest administrative appellate body for immigration law. It reviews IJ decisions and issues binding precedent decisions nationwide. The BIA generally does not hold courtroom hearings; it decides by paper review.

**Office of the Chief Administrative Hearing Officer (OCAHO)** — handles cases involving employer sanctions for illegal hiring, employment eligibility verification violations, and document fraud.

As of early 2026, the system faces a staggering backlog of over 3.3 million active pending cases — one of the most overburdened adjudicatory systems in any branch of the U.S. government.

---

## Primary Data Source: The EOIR CASE Database

### Origin and Access

EOIR's CASE database is the agency's internal case management system — the live database that immigration courts use to track their own workload. In 2008, TRAC at Syracuse University began filing FOIA requests for raw, bulk extracts of this database. Under the FOIA Improvement Act of 2016, EOIR is now required to proactively publish this data publicly because it has received at least three FOIA requests for it.

**The data is freely available from two sources:**
- **EOIR FOIA Library** (justice.gov/eoir/foia-library-0) — the official monthly release, in pipe-delimited CSV files
- **Data.gov** (catalog.data.gov/dataset/eoir-case-data) — mirrored with metadata

**Update frequency:** Monthly. EOIR releases an updated full database extract each month.

**A clean, pre-processed DuckDB version** is also available on HuggingFace (`ian-nason/eoir-database`) for immediate querying without ETL work.

---

### Historical Depth

The EOIR CASE database contains records going back to **the 1970s**, though records become substantially more complete and reliable from the mid-1980s onward (coinciding with EOIR's formal creation in 1983 and its computerization of records). Practically, most rigorous analyses treat the **early 1990s as the reliable start point** for longitudinal work, though the data's true strength is from approximately 2000 forward.

Key historical anchors:
- **1983** — EOIR formally created; immigration judge corps consolidated under DOJ
- **1997** — IIRIRA merged deportation and exclusion proceedings into unified "removal proceedings"; data structure changes at this point
- **2000s** — Electronic records become reliable and comprehensive
- **2008** — TRAC begins receiving monthly raw data extracts
- **2016** — FOIA Improvement Act mandates proactive monthly public release
- **2022** — ECAS (electronic filing system) made mandatory; data quality improves further

For a public analytics site, you can credibly publish longitudinal analysis going back **30+ years** on most major metrics.

---

## The Data in Detail: Tables and Fields

The raw EOIR CASE database contains **97 tables** and over **164 million rows** in its latest full release. Below is a breakdown of the major tables and what they contain.

### Core Tables

**`A_TblCase` — Case Demographics (12.4 million rows)**
The foundational table. One row per case (i.e., per removal proceeding). Contains:
- `IDNCASE` — unique case identifier
- `ANUMBER` — alien registration number (links individual across multiple cases)
- `NAT` — nationality code (200+ nationalities coded)
- `LANG` — language spoken
- `GENDER`
- `DATE_OF_BIRTH` (month/year only)
- `CUSTDY` — custody status (detained vs. non-detained)
- `ATTY_NBR` — attorney identifier (or flag for pro se)
- `INPUT_DATE` — date case was entered into system
- `COMP_DATE` — date case was completed
- `NTA_DATE` — date the Notice to Appear (NTA) was filed, initiating proceedings
- Respondent zip code / state / county (mailing address as recorded by court)
- Case type (`RMV` for removal, `CFF` for credible fear, `ASY` for asylum-only, etc.)

**`B_TblProceeding` — Proceedings (16.2 million rows)**
Each case can have multiple proceedings (original, remanded, reopened). Each row represents one proceeding. Contains:
- Proceeding type and status
- `IJ_CODE` — immigration judge identifier (linkable to judge name in lookup table)
- Court/hearing location
- Case outcome (`OSC_COMP` — order of removal, relief granted, dismissed, etc.)
- Decision date
- Whether appeal was filed

**`Schedule` — Hearing Entries (45.2 million rows)**
The largest table. Each scheduled hearing generates a row. Contains:
- Hearing date and time
- Adjournment reason and count (how many times rescheduled)
- Hearing medium (in-person, video, telephonic)
- Calendar type (master calendar, individual merit hearing, bond hearing, etc.)

**`Applications` — Relief Applications (15.8 million rows)**
Every application for relief filed in a proceeding. Contains:
- Application type: asylum, withholding of removal, Convention Against Torture (CAT), cancellation of removal (for LPRs and non-LPRs), adjustment of status, voluntary departure, etc.
- Decision on each application (granted, denied, withdrawn, not adjudicated, abandoned)
- Filing date and decision date

**`Charges` — DHS Charges (18.5 million rows)**
Every charge DHS filed against a respondent. Contains:
- INA section charged (e.g., 212(a)(6)(A)(i) — present without admission)
- Date charge was filed
- Whether charge was sustained or dismissed

**`Motions` — Motions Filed (8.0 million rows)**
Every motion filed in a proceeding. Contains:
- Motion type (continuance, change of venue, reopen, reconsider, terminate, etc.)
- Filing party (DHS or respondent/attorney)
- Filing method (e-filing vs. paper)
- Motion outcome (granted, denied, pending)
- Decision date

**`Representatives` — Attorney Records (25.6 million rows)**
Every attorney or accredited representative appearance. Contains:
- Attorney identifier
- Representation type (retained, pro bono, legal aid, etc.)
- Entry and withdrawal dates
- Law school/clinic affiliation (in some cases)

**`Custody_History` — Custody Status Changes (9.8 million rows)**
Full custody status change log. Contains:
- Custody status at each change (detained, released on bond, released on own recognizance, etc.)
- Date of each change
- Facility code (links to detention facility)

**`Bond` — Bond Hearings (separate table)**
Bond hearing records and decisions. Contains:
- Bond amount requested and set
- Bond decision (granted, denied)
- Deciding IJ
- Date

**`Juvenile_History` — Minor Designations (2.9 million rows)**
Records flagging cases involving minors/unaccompanied children (UAC). Critical for tracking treatment of minors across administrations.

**`Lead_Rider` — Lead/Rider Case Relationships (2.6 million rows)**
Links family unit cases together (lead case and associated "rider" cases for family members).

### Lookup Tables

EOIR uses coded values throughout. The official Code Key provides human-readable translations for:
- Nationality codes (200+ countries, including former nations like East Germany and USSR)
- Language codes
- Court location codes (70+ courts)
- IJ codes (maps to judge names)
- Charge codes (INA sections)
- Application type codes
- Motion type codes
- Outcome codes

---

## What You Can Measure

The following analytical dimensions are all available from the raw data:

### Judge-Level Analytics
- Asylum grant rate per judge (filterable by nationality, date range, case type)
- Removal order rate per judge
- In absentia order rate
- Average time to decision
- Motion grant rates (continuances, change of venue, etc.)
- Bond grant rates and bond amounts set
- Reversal rate at BIA (for judges whose decisions are appealed)
- Caseload volume over time
- Representation rate of cases before each judge

### Court/Venue Analytics
- Backlog and pending caseload by court
- Completion rates over time
- Asylum grant rate variation by court city
- New case filings by court by month
- Average case age (time from NTA filing to completion)
- Video hearing rates
- Continuance patterns by court

### Nationality Analytics
- Grant rates by nationality (200+ nationalities tracked)
- Volume trends: which nationalities are appearing more/less frequently
- Time-to-decision by nationality
- Representation rates by nationality
- Most common charges by nationality
- Countries of removal destination

### Case Outcome Analytics
- Removal orders vs. relief grants vs. dismissals vs. terminations
- In absentia order trends
- Administrative closure rates (politically sensitive — varies dramatically by administration)
- Appeals filed and BIA outcomes
- Voluntary departure grants

### Representation Analytics
- Pro se rates (cases with no attorney) — currently ~59% of 3.4M pending cases
- Grant rates: represented vs. unrepresented (one of the largest and most consistent disparities in the dataset)
- Legal aid vs. retained counsel vs. pro bono outcomes
- Attorney win rates

### Detention Analytics
- Share of cases involving detained respondents
- Grant rates: detained vs. non-detained (major disparity)
- Bond grant rates and amounts over time
- Detention facility-level patterns (via facility codes)
- Custody status changes across a proceeding

### Backlog and Timing Analytics
- Pending case counts over time (the backlog grew from ~300K in 2010 to 3.3M+ in 2026)
- Average wait time from NTA to hearing by court
- Continuance counts per case
- Cases over 5 years old, 10 years old
- Time spent on master calendar vs. individual hearing

### Political/Policy Analytics
- Administrative closure rates by administration (Obama dramatically higher; Trump restricted; Biden reopened; 2025 changes)
- Termination rates by administration
- UAC (unaccompanied children) case trends
- MPP (Migrant Protection Protocols/"Remain in Mexico") cohort outcomes
- Dedicated docket impacts
- Changes in IJ hiring rates

---

## Update Cadence and Freshness

| Source | Update Frequency | Lag |
|---|---|---|
| EOIR FOIA Library (raw data) | Monthly | ~4–6 weeks behind real-time |
| EOIR Workload & Adjudication Statistics | Quarterly (PDFs) | ~1–2 months |
| EOIR Statistical Yearbook | Annually (FY) | ~3 months post-FY close |
| TRAC Immigration Tools | Monthly | Roughly tracks EOIR release |
| Vera Institute Dashboard | Monthly | Tracks EOIR FOIA releases |

For a site that wants to lead on freshness: **pull directly from the EOIR FOIA Library monthly**, process and publish. The window between EOIR's release and a new analytics publication is your competitive moat on timeliness.

---

## Data Quality: Significant Issues to Know

This is the most important section for anyone building on this data. The EOIR data has well-documented quality problems that you must disclose and account for.

### The Disappearing Records Problem (2019–2022)
Between 2019 and 2022, TRAC documented EOIR systematically deleting records from its monthly releases. At peak, TRAC identified over 60,000 records disappearing per month. Key findings:
- Over 17,706 asylum applications disappeared from EOIR files between FY2019–FY2022
- Nearly 897,000 records were removed in a single year-over-year comparison
- Over 50,000 pending asylum applications lost track after venue changes
- EOIR initially denied the problem; a Congressional Hispanic Caucus letter and GAO investigation followed
- EOIR eventually restored most records after public pressure, but TRAC notes "persistent problems" continued at lower volumes

**For site builders:** You should archive each monthly release you download. Never replace — always append and diff. This is how TRAC maintains data integrity.

### Structural Changes Over Time
- Pre-1997 data uses different terminology (deportation/exclusion vs. removal) due to IIRIRA
- "Administrative closure" coding changed dramatically across administrations
- Application outcome codes changed: EOIR deactivated the "other" code in May 2019, replacing it with "not adjudicated"
- Expedited removal (handled by DHS/ICE, not EOIR) is NOT in this dataset — a significant scope limitation

### What's Not Included
- Cases processed through ICE expedited removal (outside EOIR jurisdiction)
- USCIS affirmative asylum decisions (only defensive asylum before IJs is here)
- Immigration court opinions/written decisions (not publicly released as text)
- Sealed or protected cases involving minors (partially present via juvenile table)

### Completeness by Era
- Pre-1990: sparse; many paper records never digitized
- 1990–2000: increasingly reliable; some fields inconsistently populated
- 2000–2016: strong; TRAC considers this the core of the reliable dataset
- 2016–present: most complete, but quality issues noted above occurred in this period

---

## Comparable and Complementary Data Sources

| Source | What It Adds | URL |
|---|---|---|
| TRAC Immigration | Cleaned, processed EOIR data; free public dashboards; some premium access | tracreports.org |
| EOIR Statistical Yearbook | Aggregate PDFs going back to the 1990s; useful for historical validation | justice.gov/eoir |
| EOIR Workload & Adjudication Statistics | 22 categories of rolling PDFs, updated quarterly | justice.gov/eoir/workload-and-adjudication-statistics |
| Vera Institute Dashboard | Legal representation rates, updated monthly | vera.org |
| Deportation Data Project | Processed EOIR data with codebook, multiple file formats | deportationdata.org |
| HuggingFace EOIR DuckDB | Pre-built queryable database, 164M rows, 97 tables | huggingface.co/datasets/ian-nason/eoir-database |
| OpenImmigration.us | Existing public judge-level analytics site | openimmigration.us |
| MobilePathways Immigration Court Data | Existing dashboards (bond, motions, asylum) | mobilepathways.org |
| BIA Precedent Decisions | Written opinions establishing immigration law precedent | justice.gov/eoir/board-of-immigration-appeals |

**Important:** OpenImmigration.us and MobilePathways already exist and do some of this work. Your differentiation should come from depth (multi-variable analysis), geographic focus (New England / Northeast), narrative framing, or specific niches (judge analytics, policy shift tracking) that these sites don't fully cover.

---

## Feature Recommendations

### Tier 1 — Core (Launch Features)

**Judge Profiles**
One page per immigration judge. Show: total cases decided, asylum grant rate (with confidence interval), removal order rate, in absentia rate, bond grant rate, average time to decision, and how each metric compares to national average. This is the single most-searched analytics use case for immigration attorneys. Filterable by date range and nationality.

**Court Profiles**
One page per immigration court (70+ courts). Show: backlog, pending cases, completion rates, average wait time, grant rates, representation rates. Allow comparison across courts.

**Nationality Dashboard**
For any of 200+ nationalities: asylum grant rate over time, most common outcome types, average case duration, which courts hear the most cases, which judges decide the most cases. Essential for practitioners preparing cases for specific nationalities.

**The Representation Gap**
A dedicated section showing the grant-rate gap between represented and unrepresented respondents, nationally and by court. This is one of the most stark and newsworthy findings in the entire dataset and consistently draws media attention.

**Backlog Tracker**
Running chart of the national pending caseload over time (1990s to present), with administrations marked. Track cases over 1 year, 3 years, 5 years old. This tells the story of decades of policy choices in one visual.

### Tier 2 — Differentiated Features

**Policy Shift Detector**
Track key metrics (administrative closure rates, termination rates, in absentia rates, continuance grant rates) with U.S. presidential administration shading. The data visually reveals every major policy shift from Reagan through the current administration. This is compelling for journalists and researchers.

**Bond Analytics**
Dedicated section on detention and bond. Grant rates by court, by judge, by nationality. Bond amounts set vs. requested. Trends over time. Detained vs. non-detained outcome disparity. Few public sites do this well.

**Motion Outcomes**
Motion-level analytics: continuance grant rates (broken down by which party filed), change of venue outcomes, motion to reopen/reconsider outcomes. Highly useful to practitioners.

**Northeast/New England Spotlight**
Given your NH base, a dedicated section on the Boston Immigration Court (which handles NH cases), plus comparison to other First Circuit-state courts (Portland ME if active, Providence RI, Hartford CT, New York). This geographic focus distinguishes you from national tools.

**In Absentia Tracker**
In absentia removal orders — issued when a respondent fails to appear — are a politically charged and frequently cited metric. Tracking them by court, by administration, by nationality, and broken down by whether the respondent was represented provides important context that raw government numbers obscure.

**UAC (Unaccompanied Children) Tracker**
Cases involving unaccompanied minors have a dedicated table in the EOIR data. A separate dashboard tracking volume, outcomes, wait times, and representation rates for minors is both analytically valuable and publicly significant.

### Tier 3 — Advanced Features

**Judge Comparison Tool**
Side-by-side judge comparison: select two or more judges, compare across all key metrics, controlling for nationality mix and case type where possible.

**Case Outcome Predictor (Descriptive)**
Not a legal predictor, but a descriptive tool: "For a Venezuelan national, represented by counsel, at the Boston Immigration Court — here is the historical outcome distribution." Make clear this is historical data, not legal advice.

**Administration-by-Administration Comparison**
A structured historical comparison of outcomes across presidential administrations, tied to specific policy changes. Grant rates, closure rates, backlog growth, judge hiring, all compared by administration with policy context.

**BIA Reversal Tracker**
The BIA data is in the proceedings table (via appeal records). Track which courts and judges have the highest BIA reversal rates — a metric that matters both for legal quality and for practitioners calculating appeal strategy.

**Data Quality Transparency Page**
Document the known EOIR data quality issues (disappearing records, administration changes, pre-1997 terminology shifts) openly. This builds credibility and distinguishes you from sites that present the data without caveats. Link to TRAC's documentation. Commit to archiving monthly releases for diff tracking.

---

## Data Modeling Recommendations

### Database Architecture

The raw EOIR data is relational and joins through consistent identifiers. Recommended schema for an analytics backend:

```
dim_judge          (judge_id, name, court, active_flag, appointment_date)
dim_court          (court_id, city, state, circuit, address)
dim_nationality    (nat_code, country_name, region, world_bank_region)
dim_attorney       (atty_id, representation_type, firm/org, pro_bono_flag)
dim_hearing_location (location_id, court_id, videoconference_flag)

fact_case          (case_id, anumber, nationality, language, gender, age_group,
                    custody_status, represented_flag, atty_id, nta_date,
                    comp_date, case_type, court_id, outcome, relief_type)

fact_proceeding    (proceeding_id, case_id, judge_id, court_id,
                    proceeding_type, decision_date, outcome_code,
                    appeal_filed_flag)

fact_application   (app_id, proceeding_id, case_id, app_type,
                    filed_date, decision_date, decision)

fact_hearing       (hearing_id, proceeding_id, scheduled_date,
                    calendar_type, medium, adjourned_flag, adjournment_reason)

fact_motion        (motion_id, proceeding_id, motion_type,
                    filing_party, filing_method, outcome, decision_date)

fact_bond          (bond_id, case_id, proceeding_id, judge_id,
                    amount_requested, amount_set, decision, hearing_date)

fact_custody       (custody_id, case_id, status, change_date, facility_code)
```

### Key Derived Metrics to Pre-Compute

These should be calculated at data load time and stored, not computed on-the-fly:

- `asylum_grant_rate` — grants / (grants + denials), excluding "other" outcomes per TRAC methodology
- `removal_rate` — removal orders / total completions
- `representation_rate` — represented cases / total cases
- `in_absentia_rate` — in absentia orders / total completions
- `median_case_age_days` — from NTA date to decision date
- `avg_hearings_per_case` — from schedule table
- `continuance_rate` — motions of type continuance granted / total continuance motions
- `bia_reversal_rate` — BIA reversals / total BIA-reviewed decisions (requires joining BIA outcomes back to IJ)

### Historical Release Versioning

Given the documented disappearing records problem, your ETL pipeline should:
1. Download each monthly release into a dated folder (never overwrite)
2. Diff each release against the prior month: log added records, modified records, and deleted records
3. Maintain a "canonical" dataset that never deletes — only marks records as "removed from EOIR release as of [date]"
4. Publish a transparency report monthly showing what changed

This is exactly what TRAC does and is what gives TRAC credibility. A commitment to this practice would be a major trust signal for your site.

---

## Audience and Monetization Context

**Primary audiences:**
- Immigration attorneys (judge analytics are directly monetizable — practitioners will pay for judge profiles before hearings)
- Journalists and editorial teams covering immigration
- Policy researchers and academics
- Immigration advocacy organizations
- Law school clinics
- Affected communities (individuals and families with pending cases)

**Content opportunities:**
- Monthly "immigration court report" tied to new data releases
- Explainers on what each metric means for practitioners
- State-by-state and court-by-court annual summaries
- Deep dives on specific nationalities when news events make them relevant (e.g., a country experiencing a political crisis)
- Policy impact analyses comparing administrations

---

## Bottom Line

The EOIR CASE database is extraordinary in its depth and public availability. No other legal dataset in the U.S. combines this volume (164M+ rows), historical length (1970s to present), individual-level detail (per-case, per-judge, per-hearing), and free monthly updates. The main challenges are data quality (well-documented and manageable with proper archiving), complexity of the relational schema, and the political sensitivity of the subject matter.

A well-designed public analytics site in this space would be genuinely useful, frequently cited, and serve an audience that is large, engaged, and currently underserved by existing tools.

---

*Sources: EOIR FOIA Library (justice.gov); TRAC at Syracuse University (tracreports.org); Deportation Data Project (deportationdata.org); Congressional Research Service; GAO; Vera Institute; HuggingFace EOIR Database; OpenImmigration.us*
