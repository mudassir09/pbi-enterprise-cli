---
name: power-bi-templates
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use when the user wants a ready-made Power BI solution scaffold for a specific
  business domain. Triggers on: "template", "starter", "scaffold for sales",
  "build a finance dashboard", "HR report template", "operations dashboard",
  "marketing analytics starter", "give me a starting point for". Also triggers
  when domain is clear (Sales, Finance, HR, Operations, Marketing) and user wants
  to start from scratch. Do NOT trigger for custom one-off reports.
---

# power-bi-templates

## Universal KPI Scaffold

Every domain template starts with this page structure:

```
Page 1: Executive Summary
  - 4× KPI Cards (primary metrics)
  - 1× Line Chart (trend, 12 months)
  - 1× Bar Chart (top N breakdown)

Page 2: Detail / Drill-through
  - Matrix (full breakdown by all dimensions)
  - Slicers (period, region, category)

Page 3: Trend Analysis
  - Combo chart (actuals vs target vs prior year)
  - YOY% KPI card

Page 4: Data Quality / Governance
  - Row count cards per table
  - Last refresh timestamp
  - Missing data alerts
```

---

## Template 1: Sales Analytics

### Schema
```
FactSales       — OrderID, DateKey, ProductKey, CustomerKey, SalesRepKey,
                  Qty, UnitPrice, Discount, NetRevenue, CostOfGoods
DimDate         — standard date table with fiscal year
DimProduct      — ProductKey, Category, SubCategory, ProductName, UnitCost
DimCustomer     — CustomerKey, Name, Region, Segment, Country
DimSalesRep     — SalesRepKey, Name, Team, Manager
```

### Core Measures (15)
```dax
[Total Revenue]           = SUMX(FactSales, FactSales[Qty] * FactSales[UnitPrice])
[Total Cost]              = SUMX(FactSales, FactSales[Qty] * FactSales[CostOfGoods])
[Gross Margin]            = [Total Revenue] - [Total Cost]
[Gross Margin %]          = DIVIDE([Gross Margin], [Total Revenue])
[Units Sold]              = SUM(FactSales[Qty])
[Average Order Value]     = DIVIDE([Total Revenue], DISTINCTCOUNT(FactSales[OrderID]))
[Revenue YTD]             = TOTALYTD([Total Revenue], DimDate[Date])
[Revenue PYTD]            = CALCULATE([Revenue YTD], SAMEPERIODLASTYEAR(DimDate[Date]))
[Revenue YOY %]           = DIVIDE([Revenue YTD] - [Revenue PYTD], [Revenue PYTD])
[Revenue LM]              = CALCULATE([Total Revenue], PREVIOUSMONTH(DimDate[Date]))
[Revenue vs LM %]         = DIVIDE([Total Revenue] - [Revenue LM], [Revenue LM])
[Top N Customers Revenue] = CALCULATE([Total Revenue], TOPN(10, DimCustomer, [Total Revenue]))
[Running Total Revenue]   = CALCULATE([Total Revenue], DATESYTD(DimDate[Date]))
[Revenue per Customer]    = DIVIDE([Total Revenue], DISTINCTCOUNT(FactSales[CustomerKey]))
[Win Rate]                = DIVIDE(COUNTROWS(FILTER(FactSales, FactSales[Status]="Won")), COUNTROWS(FactSales))
```

### CLI scaffold
```bash
pbi source scaffold --source "mssql://server/SalesDW" \
  --output ./SalesAnalytics.SemanticModel/definition/ \
  --date-table-strategy generate
```

---

## Template 2: Finance Reporting

### Schema
```
FactGL          — JournalID, DateKey, AccountKey, CostCentreKey, Amount, DrCr
DimAccount      — AccountKey, AccountCode, AccountName, Category (P&L/BS/CF)
DimCostCentre   — CostCentreKey, Name, Department, Manager
DimDate         — standard + fiscal year + fiscal period
DimScenario     — Actual, Budget, Forecast
```

### Core Measures (10)
```dax
[Total Amount]     = SUM(FactGL[Amount])
[Revenue]          = CALCULATE([Total Amount], DimAccount[Category]="Revenue")
[Expenses]         = CALCULATE([Total Amount], DimAccount[Category]="Expense")
[Net Profit]       = [Revenue] - [Expenses]
[Net Profit %]     = DIVIDE([Net Profit], [Revenue])
[Budget Variance]  = CALCULATE([Total Amount], DimScenario[Name]="Actual")
                   - CALCULATE([Total Amount], DimScenario[Name]="Budget")
[Budget Var %]     = DIVIDE([Budget Variance], CALCULATE([Total Amount], DimScenario[Name]="Budget"))
[YTD P&L]         = TOTALYTD([Net Profit], DimDate[Date])
[Prior Year P&L]  = CALCULATE([YTD P&L], SAMEPERIODLASTYEAR(DimDate[Date]))
[P&L YOY %]       = DIVIDE([YTD P&L] - [Prior Year P&L], ABS([Prior Year P&L]))
```

---

## Template 3: HR Analytics

### Schema
```
FactHeadcount   — EmployeeKey, DateKey, DepartmentKey, IsActive, Salary
FactAttrition   — EmployeeKey, TermDateKey, Reason, Type (voluntary/involuntary)
DimEmployee     — EmployeeKey, Name, Title, Band, HireDate, ManagerKey
DimDepartment   — DepartmentKey, Name, Division, CostCentre
DimDate         — standard
```

### Core Measures (8)
```dax
[Active Headcount]    = CALCULATE(COUNTROWS(FactHeadcount), FactHeadcount[IsActive]=TRUE())
[Attrition Count]     = COUNTROWS(FactAttrition)
[Attrition Rate]      = DIVIDE([Attrition Count], [Active Headcount])
[Avg Salary]          = AVERAGE(FactHeadcount[Salary])
[Salary Cost]         = SUM(FactHeadcount[Salary])
[Tenure Avg Years]    = AVERAGEX(DimEmployee, DATEDIFF(DimEmployee[HireDate], TODAY(), YEAR))
[New Hires MTD]       = CALCULATE(COUNTROWS(DimEmployee), DATESMTD(DimDate[Date]))
[Voluntary Attrition] = CALCULATE([Attrition Count], FactAttrition[Type]="voluntary")
```

> **Note:** Apply RLS by department before the first demo. See `power-bi-rls-security`.

---

## Template 4: Operations

### Schema
```
FactOrders       — OrderID, DateKey, ProductKey, WarehouseKey, Qty, LeadTimeDays, Status
FactInventory    — ProductKey, DateKey, WarehouseKey, StockOnHand, ReorderPoint
DimProduct, DimWarehouse, DimDate
```

---

## Template 5: Marketing

### Schema
```
FactCampaign     — CampaignID, DateKey, ChannelKey, Impressions, Clicks, Conversions, Spend
FactLeads        — LeadID, DateKey, CampaignID, Stage, Revenue
DimChannel       — Digital, Email, Social, Events, Paid Search
DimDate, DimCampaign
```

---

## Getting Started with Any Template

1. Run `pbi skills install power-bi-templates` to install this skill.
2. Profile your source: `pbi source profile --source <connection>`.
3. Scaffold: `pbi source scaffold --output ./MyProject.SemanticModel/definition/`.
4. Govern: `pbi govern check` — fix naming before adding measures.
5. Add measures: use the DAX above as a starting point.
6. Test: `pbi dax test --suite tests/measures.yaml`.
7. Deploy: `pbi deploy push --workspace "Dev"`.
