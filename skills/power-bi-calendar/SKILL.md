---
name: power-bi-calendar
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for generating and managing Calendar/Date dimension tables in Power BI: creating
  standard or fiscal-year calendars, adding time intelligence columns, configuring the
  mark-as-date-table setting, and scaffolding DAX calendar expressions. Triggers on:
  "calendar table", "date table", "date dimension", "fiscal year", "mark as date table",
  "time intelligence columns", "pbi calendar", "generate calendar", "date scaffold".
version: "1.0"
---

# power-bi-calendar

## Quick Reference

```bash
# Generate a standard calendar table (2015–2030)
pbi calendar generate --start 2015 --end 2030

# Generate a fiscal-year calendar (year ends 30 June)
pbi calendar generate --start 2015 --end 2030 --fiscal-year-end "06-30"

# Generate and mark as the model's date table automatically
pbi calendar generate --start 2015 --end 2030 --mark-as-date-table

# Add time intelligence columns to an existing Calendar table
pbi calendar enrich --table Calendar

# Show current date-table configuration
pbi calendar status

# Validate that Calendar covers all dates in fact tables
pbi calendar validate --fact-tables "Sales,Orders,Returns"
```

---

## Generated Calendar Columns

`pbi calendar generate` creates a calculated table with the following columns by default:

| Column | Type | Example |
|--------|------|---------|
| `Date` | Date | 2024-03-15 |
| `Year` | Integer | 2024 |
| `Quarter` | Integer | 1 |
| `QuarterLabel` | Text | "Q1 2024" |
| `Month` | Integer | 3 |
| `MonthName` | Text | "March" |
| `MonthShort` | Text | "Mar" |
| `Week` | Integer | 11 |
| `DayOfWeek` | Integer | 5 (Friday) |
| `DayName` | Text | "Friday" |
| `IsWeekday` | Boolean | TRUE |
| `IsWeekend` | Boolean | FALSE |
| `IsToday` | Boolean | FALSE |

### Fiscal year columns (with `--fiscal-year-end`)

| Column | Example (FY end 30 Jun) |
|--------|------------------------|
| `FiscalYear` | 2024 (Jul 2023 – Jun 2024) |
| `FiscalQuarter` | 3 |
| `FiscalMonth` | 9 |
| `FiscalYearLabel` | "FY2024" |

---

## DAX Calendar Expressions

`pbi calendar generate` writes one of these DAX expressions depending on flags:

### Standard calendar

```dax
Calendar =
ADDCOLUMNS(
    CALENDAR(DATE(2015,1,1), DATE(2030,12,31)),
    "Year",         YEAR([Date]),
    "Quarter",      QUARTER([Date]),
    "QuarterLabel", "Q" & QUARTER([Date]) & " " & YEAR([Date]),
    "Month",        MONTH([Date]),
    "MonthName",    FORMAT([Date], "MMMM"),
    "MonthShort",   FORMAT([Date], "MMM"),
    "Week",         WEEKNUM([Date]),
    "DayOfWeek",    WEEKDAY([Date], 2),
    "DayName",      FORMAT([Date], "dddd"),
    "IsWeekday",    WEEKDAY([Date], 2) <= 5,
    "IsWeekend",    WEEKDAY([Date], 2) > 5,
    "IsToday",      [Date] = TODAY()
)
```

### Fiscal year calendar (FY end 30 June)

```dax
-- Fiscal year starts 1 July; FY2024 = Jul 2023 – Jun 2024
"FiscalYear",    IF(MONTH([Date]) >= 7, YEAR([Date]) + 1, YEAR([Date])),
"FiscalMonth",   MOD(MONTH([Date]) - 7 + 12, 12) + 1,
"FiscalQuarter", INT((MOD(MONTH([Date]) - 7 + 12, 12)) / 3) + 1
```

---

## Mark as Date Table

Power BI Time Intelligence functions (TOTALYTD, SAMEPERIODLASTYEAR, etc.) require the
Calendar table to be marked as the model's date table.

```bash
pbi calendar mark-as-date-table --table Calendar --date-column Date
```

Or pass `--mark-as-date-table` to `pbi calendar generate` to do it in one step.

Requirements:
- The date column must have one row per date with no gaps or duplicates.
- The date column must have no blank values.
- The date range must cover all dates present in all related fact tables.

Run `pbi calendar validate` to check these requirements automatically.

---

## Calendar Validation

```bash
pbi calendar validate --fact-tables "Sales,Orders"

✓ Calendar[Date] covers all dates in Sales[OrderDate] (2018-01-01 – 2024-12-31)
✗ Calendar[Date] does NOT cover all dates in Orders[ShipDate]
    Missing range: 2017-06-01 – 2017-12-31 (earliest ShipDate precedes Calendar start)
    Fix: pbi calendar generate --start 2017 --end 2030 --mark-as-date-table

✓ No duplicate dates in Calendar[Date]
✓ No blank dates in Calendar[Date]
```

---

## Best Practices

| Recommendation | Why |
|----------------|-----|
| Use a calculated table (DAX), not a loaded table | Stays in sync; no refresh needed |
| Set `--start` 1–2 years before earliest fact date | Avoids validation failures after historical load |
| Always `--mark-as-date-table` | Required for Time Intelligence DAX functions |
| Use a single Calendar table for the whole model | Multiple date tables cause filter context confusion |
| Hide key columns (`Month`, `Week`) from report | Use `MonthName` and `QuarterLabel` in visuals instead |
