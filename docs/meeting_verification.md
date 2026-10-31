# Announcement spot checks

Reviewed against original source wording during implementation on 2026-10-30.
This is agent-assisted manual inspection, not an independent human adjudication.
All 207 scheduled decisions in 2000–2025 also pass the numerical announcement
parser. The primary model uses the 159 decisions from 2006 onward.

| Decision | Before → after (%) | Class | Check / source |
|---|---|---|---|
| 2004-06-30 | 1.00 → 1.25 | hike | [Statement](https://www.federalreserve.gov/boarddocs/press/monetary/2004/20040630/default.htm): single target, +25 bp |
| 2006-06-29 | 5.00 → 5.25 | hike | [Statement](https://www.federalreserve.gov/newsevents/press/monetary/20060629a.htm): end of tightening cycle, +25 bp |
| 2007-06-28 | 5.25 → 5.25 | hold | [Statement](https://www.federalreserve.gov/newsevents/press/monetary/20070618a.htm): release header June 28 despite June 18 URL slug |
| 2008-01-22 | 4.25 → 3.50 | cut, unscheduled | [Statement](https://www.federalreserve.gov/newsevents/press/monetary/20080122b.htm): −75 bp, published the day after the conference call |
| 2008-01-30 | 3.50 → 3.00 | cut | [Statement](https://www.federalreserve.gov/newsevents/press/monetary/20080130a.htm): −50 bp relative to the target **after** January 22 |
| 2008-12-16 | 1.00 → [0, 0.25] | cut | [Statement](https://www.federalreserve.gov/newsevents/press/monetary/20081216b.htm): range transition, midpoint change −87.5 bp |
| 2015-12-16 | [0, 0.25] → [0.25, 0.50] | hike | [Statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20151216a.htm): both bounds +25 bp |
| 2019-07-31 | [2.25, 2.50] → [2.00, 2.25] | cut | [Statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20190731a.htm): −25 bp, 14:00 EDT |
| 2020-03-03 | [1.50, 1.75] → [1.00, 1.25] | cut, unscheduled | [Statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20200303a.htm): −50 bp, 10:00 EST |
| 2020-03-15 | [1.00, 1.25] → [0, 0.25] | cut, unscheduled | [Statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm): −100 bp, 17:00 EDT |
| 2020-04-29 | [0, 0.25] → [0, 0.25] | hold | [Statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20200429a.htm): earlier emergency cuts are separate events |
| 2024-09-18 | [5.25, 5.50] → [4.75, 5.00] | cut | [Statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20240918a.htm): −50 bp |
| 2025-12-10 | [3.75, 4.00] → [3.50, 3.75] | cut | [Statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20251210a.htm): −25 bp |

Additional classification reviews:

- [September 15, 2003](https://www.federalreserve.gov/fomc/minutes/20030812.htm)
  was a communications discussion; the minutes explicitly identify September 16
  as the next regular meeting. Do not create an extra target row.
- [March 17–18, 2020](https://www.federalreserve.gov/monetarypolicy/fomchistorical2020.htm)
  is explicitly cancelled. Its hypothetical scheduled forecast convention is
  March 11 at 18:00 EDT. March 15 intervenes; no realized scheduled target exists.
- Liquidity facilities and discount-rate changes do not automatically change
  the funds target. Reviewed non-target statements appear in
  `configs/announcement_reviews.yaml`.
- The March 23, 2020 directive reaffirms a 0–0.25% range; parsing its upper bound
  as a single 0.25% target would create a spurious hike and subsequent cut.

Early 1994 statements often describe reserve pressure without stating a numerical
target, and many early holds have no linked contemporary statement. Those rows
retain null labels/statuses in the inventory and do not enter training. Extending
the primary sample requires targeted archival verification, not effective-rate proxies.
