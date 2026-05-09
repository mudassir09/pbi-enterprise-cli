---
name: power-bi-testing
description: >
  Use for testing Power BI semantic models and DAX measures: unit tests,
  YAML test fixtures, CI test gates, regression testing, and assertion patterns.
  Triggers on: "test", "unit test", "dax test", "measure test", "pbi dax test",
  "test fixture", "regression test", "CI gate", "assert", "expected value".
version: "1.0"
---

# power-bi-testing

## Quick Reference

```bash
# Run all DAX tests
pbi dax test

# Run tests from a specific file
pbi dax test --file tests/measures.yaml

# Run tests and output JUnit XML (for CI)
pbi dax test --junit test-results.xml

# Validate a single DAX expression
pbi dax validate "CALCULATE(SUM(Sales[Revenue]), Sales[Region] = \"East\")"

# Run a DAX query and inspect results
pbi dax query "EVALUATE ROW(\"Total\", SUM(financials[Sales]))"
```

---

## Test File Format (YAML)

Test files live in `tests/` at the project root:

```yaml
# tests/measures.yaml
version: "1.0"
connection: auto  # auto-detect running Power BI Desktop instance

tests:
  - name: "Total Sales basic aggregation"
    dax: |
      EVALUATE ROW("Result", SUM(financials[Sales]))
    assert:
      - column: "Result"
        row: 0
        expected: 118726350.26
        tolerance: 0.01  # allow 1% variance

  - name: "Sales filtered to Government segment"
    dax: |
      EVALUATE
      CALCULATETABLE(
        ROW("Result", SUM(financials[Sales])),
        financials[Segment] = "Government"
      )
    assert:
      - column: "Result"
        row: 0
        expected: 52000000
        tolerance: 0.05

  - name: "Year slicer produces correct row count"
    dax: |
      EVALUATE
      SUMMARIZE(financials, financials[Year])
    assert:
      - row_count: 4

  - name: "Profit Margin % is between 0 and 100"
    dax: |
      EVALUATE
      SUMMARIZE(financials, financials[Country], "Margin", [Profit Margin %])
    assert:
      - column: "Margin"
        all_rows_between: [0, 100]

  - name: "No blank countries"
    dax: |
      EVALUATE
      FILTER(
        SUMMARIZE(financials, financials[Country]),
        ISBLANK(financials[Country])
      )
    assert:
      - row_count: 0
```

---

## Assertion Types

| Assertion | Checks | Example |
|-----------|--------|---------|
| `expected` | Exact value (with optional tolerance) | `expected: 1234567` |
| `expected_string` | Exact string match | `expected_string: "Government"` |
| `row_count` | Number of rows returned | `row_count: 5` |
| `min_rows` | At least N rows | `min_rows: 1` |
| `max_rows` | At most N rows | `max_rows: 100` |
| `all_rows_between` | Every value in range | `all_rows_between: [0, 100]` |
| `not_blank` | No BLANK() values | `not_blank: true` |
| `unique` | All values distinct | `unique: true` |

---

## Test Categories

### Sanity Tests

Check basic model integrity:

```yaml
- name: "Date table is contiguous"
  dax: |
    EVALUATE ROW("Gaps",
      COUNTROWS(Date) - DATEDIFF(MIN(Date[Date]), MAX(Date[Date]), DAY) - 1
    )
  assert:
    - column: "Gaps"
      row: 0
      expected: 0

- name: "All Sales rows have a valid Date"
  dax: |
    EVALUATE ROW("Orphans",
      COUNTROWS(FILTER(Sales, ISBLANK(RELATED(Date[Date]))))
    )
  assert:
    - column: "Orphans"
      row: 0
      expected: 0
```

### Regression Tests

Lock in known-good values after model changes:

```yaml
- name: "Total Revenue matches source system (regression)"
  dax: |
    EVALUATE ROW("Total", [Total Revenue])
  assert:
    - column: "Total"
      row: 0
      expected: 118726350.26
      tolerance: 0.001  # tight — no regressions allowed
```

### DAX Logic Tests

Test specific business logic:

```yaml
- name: "YTD resets at year boundary"
  dax: |
    EVALUATE
    CALCULATETABLE(
      ROW("YTD", [Revenue YTD]),
      Date[Date] = DATE(2023, 1, 1)
    )
  assert:
    - column: "YTD"
      row: 0
      # First day of year: YTD should equal daily revenue only
      min_rows: 1
      not_blank: true
```

---

## CI Integration

### GitHub Actions

```yaml
name: DAX Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start Power BI Desktop
        run: Start-Process -FilePath "PBIDesktop.exe" -ArgumentList "financials.pbip"
      - name: Wait for model to load
        run: Start-Sleep -Seconds 15
      - name: Run DAX tests
        run: pbi dax test --junit test-results.xml
      - name: Publish results
        uses: dorny/test-reporter@v1
        with:
          name: DAX Test Results
          path: test-results.xml
          reporter: java-junit
```

### JUnit XML Output

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="DAX Tests" tests="5" failures="1" time="2.34">
    <testcase name="Total Sales basic aggregation" time="0.45"/>
    <testcase name="Sales filtered to Government" time="0.38">
      <failure message="Expected 52000000, got 51987234 (delta: 12766, tolerance: 2600000)"/>
    </testcase>
  </testsuite>
</testsuites>
```

---

## Running Tests Against Live Model

`pbi dax test` connects to the running Power BI Desktop instance via ADOMD.NET:

```
Power BI Desktop (open with financials.pbip)
         ↓
pbi dax test
         ↓
ADOMD connection to msmdsrv.exe on localhost:{port}
         ↓
Execute each test DAX query
         ↓
Assert results → PASS / FAIL
```

Prerequisites:
- Power BI Desktop must be open with the target .pbip file
- Run `pbi connect` first to verify connection
- Model must be refreshed (data loaded)

---

## Common Test Failures

| Failure | Cause | Fix |
|---------|-------|-----|
| `Connection refused` | Desktop not running | Open .pbip in Power BI Desktop |
| `Column not found` | Schema changed | Update test DAX to new column name |
| Value off by large margin | Incomplete refresh | Refresh the model in Desktop |
| `BLANK()` where number expected | Filter context issue | Check measure CALCULATE context |
| Flaky test | Non-deterministic data | Use `row_count` instead of exact value |
