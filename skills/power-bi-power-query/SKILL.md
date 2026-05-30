---
name: power-bi-power-query
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for Power Query M language: ETL transformations, data shaping, REST API
  connectors, query folding, incremental refresh parameters, and date table
  generation in M. Triggers on: "Power Query", "M code", "let...in", "transform",
  "combine tables", "unpivot", "custom connector", "incremental refresh", "REST API
  in Power Query", "SharePoint connector". Do NOT trigger for DAX or data modelling.
---

# power-bi-power-query

## M Language Fundamentals

Every M query follows the `let...in` structure:

```m
let
    Source      = Sql.Database("server", "db"),
    SalesTable  = Source{[Schema="dbo", Item="FactSales"]}[Data],
    Filtered    = Table.SelectRows(SalesTable, each [Year] = 2026),
    Renamed     = Table.RenameColumns(Filtered, {{"SalesAmt", "Revenue"}})
in
    Renamed
```

Rules:
- Each step name must be unique within the query.
- Reference earlier steps by name; avoid repeating transformations.
- The `in` clause is the single output of the query.

---

## Key Transformations

### Unpivot (wide → tall)

```m
Table.UnpivotOtherColumns(Source, {"Product"}, "Month", "Sales")
```

### Merge (JOIN equivalent)

```m
Table.NestedJoin(
    Orders, {"CustomerID"},
    Customers, {"ID"},
    "CustomerData",
    JoinKind.LeftOuter
)
```

### Group By (aggregate)

```m
Table.Group(Source, {"Region"}, {
    {"TotalSales", each List.Sum([Sales]), type number},
    {"OrderCount", each Table.RowCount(_), type number}
})
```

### Conditional column

```m
Table.AddColumn(Source, "Tier", each
    if [Revenue] > 100000 then "Gold"
    else if [Revenue] > 50000 then "Silver"
    else "Bronze"
)
```

---

## Date Table in M (auto-generated)

```m
let
    StartDate   = #date(2020, 1, 1),
    EndDate     = Date.From(DateTime.LocalNow()),
    Duration    = Duration.Days(EndDate - StartDate) + 1,
    DateList    = List.Dates(StartDate, Duration, #duration(1,0,0,0)),
    DateTable   = Table.FromList(DateList, Splitter.SplitByNothing(), {"Date"}),
    TypedDates  = Table.TransformColumnTypes(DateTable, {{"Date", type date}}),
    Year        = Table.AddColumn(TypedDates, "Year", each Date.Year([Date]), Int64.Type),
    Month       = Table.AddColumn(Year, "Month", each Date.Month([Date]), Int64.Type),
    MonthName   = Table.AddColumn(Month, "MonthName", each Date.ToText([Date], "MMMM"), type text),
    Quarter     = Table.AddColumn(MonthName, "Quarter", each "Q" & Text.From(Date.QuarterOfYear([Date])), type text),
    WeekDay     = Table.AddColumn(Quarter, "DayOfWeek", each Date.DayOfWeekName([Date]), type text),
    IsWeekend   = Table.AddColumn(WeekDay, "IsWeekend", each Date.DayOfWeek([Date]) >= 5, type logical)
in
    IsWeekend
```

---

## REST API with Pagination

```m
let
    GetPage = (url as text) =>
        let
            Response   = Web.Contents(url, [Headers=[Authorization="Bearer " & ApiKey]]),
            Json       = Json.Document(Response),
            Rows       = Json[data],
            NextUrl    = try Json[nextLink] otherwise null
        in
            {Rows, NextUrl},

    AllPages = List.Generate(
        () => GetPage(BaseUrl),
        each _[0] <> null,
        each if _[1] <> null then GetPage(_[1]) else {null, null}
    ),
    Combined = List.Combine(List.Transform(AllPages, each _[0])),
    Result   = Table.FromList(Combined, Splitter.SplitByNothing())
in
    Result
```

---

## Query Folding

Query folding pushes transformations back to the source database as SQL.
**Always check** if folding is active (right-click step → "View Native Query").

Rules that **break** folding (avoid early in query):
- `Table.Buffer()`
- Custom functions on individual cells
- Merges with non-foldable sources
- `Table.AddColumn` with complex M logic

Keep foldable steps (filter, select columns, rename) **before** non-foldable ones.

---

## Incremental Refresh Parameters

```m
// In Power Query Editor → Manage Parameters:
// RangeStart  (Date/Time, required)
// RangeEnd    (Date/Time, required)

let
    Source   = Sql.Database("server", "db"),
    Filtered = Table.SelectRows(Source{[Item="FactSales"]}[Data], each
        [OrderDate] >= RangeStart and [OrderDate] < RangeEnd
    )
in
    Filtered
```

Parameter names **must** be exactly `RangeStart` and `RangeEnd`.

---

## Error Handling

```m
// Safe column access
Table.AddColumn(Source, "SafeValue", each try [Amount] otherwise 0)

// Try/otherwise pattern
let Result = try SomeDangerousStep otherwise null in Result

// Replace errors in a column
Table.ReplaceErrorValues(Source, {{"Amount", 0}})
```

---

## Connector Patterns

| Source | M function |
|--------|-----------|
| SQL Server | `Sql.Database(server, db)` |
| SharePoint list | `SharePoint.Tables(siteUrl)` |
| OneDrive Excel | `Excel.Workbook(Web.Contents(url))` |
| Dataverse | `CommonDataService.Database(env)` |
| OData | `OData.Feed(url)` |
| REST JSON | `Json.Document(Web.Contents(url, [Headers=[...]]))` |
| Fabric Lakehouse | `AzureStorage.DataLake(adlsUrl)` |
