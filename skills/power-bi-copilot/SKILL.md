---
name: power-bi-copilot
version: "1.0"
min_cli_version: "4.0.0"
description: >
  Use for Power BI Copilot setup, Q&A synonyms, Smart Narratives, linguistic schema,
  AI visuals (Key Influencers, Decomposition Tree, Anomaly Detection), and dataset
  optimisation for Copilot. Triggers on: "Copilot", "Q&A", "Smart Narratives",
  "Key Influencers", "Decomposition Tree", "Anomaly Detection", "linguistic schema",
  "synonyms", "natural language", "AI visual". Do NOT trigger for standard DAX.
---

# power-bi-copilot

## Copilot Requirements

| Requirement | Detail |
|-------------|--------|
| Licence | Power BI Premium Per User (PPU) or P/F-SKU |
| Region | Copilot must be enabled in your tenant region |
| Workspace | Must be on a Premium or Fabric capacity |
| Language | English (additional languages in preview) |
| Admin setting | Power BI Admin Portal → Copilot and Azure OpenAI → Enable |

---

## Dataset Optimisation for Copilot

Copilot generates DAX using the measures and columns it can "see". Better metadata
→ better Copilot answers.

### 1. Add descriptions to every measure

```tmdl
measure 'Total Revenue' = SUMX(FactSales, FactSales[Qty] * FactSales[UnitPrice])
  formatString: "$#,##0"
  displayFolder: "Revenue"
  description: "Total net revenue after discounts, excluding tax."
```

CLI:
```bash
pbi measure update --table _Measures --name "Total Revenue" \
  --description "Total net revenue after discounts, excluding tax."
```

### 2. Hide technical columns from Q&A

Any column used only for joins or internal logic should be hidden:

```bash
pbi model columns --table FactSales --set-hidden "SalesOrderID,ProductKey,DateKey"
```

### 3. Set isHidden=false on business-facing columns only

Copilot respects `isHidden`. Expose only columns a business user would query.

### 4. Mark the date table

```bash
pbi model tables --mark-date-table DimDate --date-column Date
```

---

## Q&A Synonyms

Q&A uses synonyms to understand natural language variations:

```json
// In the semantic model definition or via Power BI Desktop:
{
  "table": "FactSales",
  "synonyms": ["sales", "orders", "transactions", "revenue data"]
}
{
  "column": "FactSales[NetRevenue]",
  "synonyms": ["revenue", "sales amount", "income", "net sales"]
}
```

Add synonyms via: Power BI Desktop → Q&A setup → Synonyms tab.

---

## Linguistic Schema

The linguistic schema teaches Q&A grammar — how to phrase questions about your data:

```yaml
# linguistic_schema.yaml (Power BI Desktop Q&A setup)
Entities:
  - Name: Product
    Binding:
      Table: DimProduct
    Synonyms: [item, SKU, article]
Relationships:
  - Name: sells
    Subject: Customer
    Object: Product
    Binding:
      Table: FactSales
```

---

## Smart Narratives with DAX

Smart Narratives can include dynamic DAX values in text:

```
"Revenue for [SELECTEDVALUE(DimDate[MonthName])] was 
[FORMAT([Total Revenue], "$#,##0")] which is 
[FORMAT([YOY Revenue Growth %], "+0.0%;-0.0%")] vs last year."
```

Use `FORMAT()` to control number presentation in narrative text.

---

## AI Visuals

### Key Influencers
Explains what drives a metric up or down. Best practices:
- Use a categorical or binary target (e.g., "Churn: Yes/No").
- Limit to < 20 explanatory fields — too many dilutes the analysis.
- Requires at least 100 rows per segment.

### Decomposition Tree
Breaks a measure down by multiple dimensions interactively:
- Pin the first split to a known dimension (e.g., Region).
- Use "High value" / "Low value" AI splits to find surprising drivers.

### Anomaly Detection
Automatically highlights data points that deviate from the expected trend:
- Works on line charts only.
- Configure sensitivity (1–10) and expected seasonality.
- Available in report view, not embedded.

---

## Copilot Prompting Tips for End Users

Teach users to ask:
- "Summarise the sales performance this quarter"
- "Create a line chart of revenue by month"
- "What drove the spike in returns in March?"
- "Explain this visual" (Copilot narrative)

Copilot **cannot**:
- Write Power Query M code
- Modify the data model
- Access data outside the published dataset
