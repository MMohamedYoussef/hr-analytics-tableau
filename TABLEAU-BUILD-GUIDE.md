# Tableau Public workbook build guide

The repository includes a working native Tableau packaged workbook at `assets/hr_analytics.twbx` with the monthly data embedded, two sheets, and a dashboard. The PNG and Plotly HTML are companion previews. This guide documents the data model and additional calculations you can add to extend the current workbook. A Tableau Public URL has not been published.

## Connect and prepare

1. In Tableau Public, connect to the text file at assets/monthly_department_metrics.csv.
2. Confirm month is a Date, department is a string dimension, and the remaining columns are numeric measures.
3. Keep one row per month and department. There are 96 rows: January 2024 through December 2025, four departments per month.
4. Use the employee ledger at assets/employees.csv only for audit or a future drill-down sheet. Do not join it directly to the monthly table; that would multiply the pre-aggregated metrics.

## Calculated fields

Create these fields, then format rates as percentages with one decimal place:

**Monthly separation rate**

~~~tableau
SUM([separations]) / SUM([avg_headcount])
~~~

Place month in the view so each mark represents a calendar month. This aggregates numerator and denominator correctly across selected departments. Do not average the row-level turnover_rate values.

**2025 annual turnover**

~~~tableau
SUM(IF YEAR([month]) = 2025 THEN [separations] ELSE 0 END)
/
(SUM(IF YEAR([month]) = 2025 THEN [avg_headcount] ELSE 0 END) / 12)
~~~

The denominator is the mean of twelve monthly average headcounts. Keep all twelve 2025 months in the data source for this field. Department filters are safe; a general month filter that removes 2025 rows changes its meaning.

**2025 ending headcount**

~~~tableau
SUM(IF [month] = #2025-12-01# THEN [end_headcount] ELSE 0 END)
~~~

**2025 hires**

~~~tableau
SUM(IF YEAR([month]) = 2025 THEN [hires] ELSE 0 END)
~~~

**2025 separations**

~~~tableau
SUM(IF YEAR([month]) = 2025 THEN [separations] ELSE 0 END)
~~~

## Worksheets and dashboard

Use a fixed 1600 × 900 dashboard canvas, dark navy background #0D1726, card surface #152438, cyan #58D6DD for headcount, coral #FF9278 for separations, and muted text #9EB3C7.

| Sheet | Tableau construction |
| --- | --- |
| Headcount trend | Month (continuous month/date) on Columns, SUM(end_headcount) on Rows, line mark, January 2024–December 2025. |
| Monthly separation rate | Month on Columns, Monthly separation rate on Rows, bars, percentage axis. |
| Turnover by department | Department on Rows, 2025 annual turnover on Columns, horizontal bars sorted descending, percentage labels. |
| Four KPI cards | One sheet each for 2025 ending headcount, 2025 hires, 2025 separations, and 2025 annual turnover. |

Place KPI cards across the top, headcount line on the left, department bars on the right, and monthly rate under the line. Add a short note explaining the turnover denominator. Expose Department as a single dashboard filter and apply it to all seven worksheets. Preserve the same definitions when a department is selected.

## Reconciliation before publishing

With all departments selected, confirm these exact source-data values:

| KPI | Expected |
| --- | ---: |
| December 2025 ending headcount | 319 |
| 2025 hires | 164 |
| 2025 separations | 100 |
| 2025 annual turnover | 34.682081% (34.7% displayed) |

Save the validated workbook as a packaged Tableau workbook (.twbx), capture a genuine Tableau screenshot, and only then publish to Tableau Public and add its real URL to README.md. The screenshot and source workbook should show matching figures.
