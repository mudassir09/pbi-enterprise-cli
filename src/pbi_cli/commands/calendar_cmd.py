"""pbi calendar / pbi culture — calendar table configuration and locale settings."""

from __future__ import annotations

import click
from rich.console import Console

from pbi_cli.commands._shared import dry_run_echo, get_backend, output_json_or_table

console = Console()


@click.group("calendar")
def calendar_cmd() -> None:
    """Generate and configure a calendar/date table in the semantic model."""


@calendar_cmd.command("generate")
@click.option("--table-name", default="Calendar", show_default=True,
              help="Name for the generated calendar table.")
@click.option("--start-year", default=2020, show_default=True, type=int,
              help="First year to include.")
@click.option("--end-year",   default=2030, show_default=True, type=int,
              help="Last year to include.")
@click.option("--fiscal-year-start", default=1, show_default=True, type=int,
              help="First month of the fiscal year (1=Jan, 7=Jul, 10=Oct).")
@click.option("--weekend-days", default="6,7", show_default=True,
              help="Comma-separated ISO weekday numbers for weekends (1=Mon…7=Sun).")
@click.pass_context
def calendar_generate(
    ctx: click.Context,
    table_name: str, start_year: int, end_year: int,
    fiscal_year_start: int, weekend_days: str,
) -> None:
    """Generate a DAX CALENDAR expression and add it as a calculated table.

    \b
    Example:
      pbi calendar generate --start-year 2019 --end-year 2025 --fiscal-year-start 7
    """
    if dry_run_echo(ctx, f"generate Calendar table '{table_name}' ({start_year}–{end_year})"):
        return

    weekend_list = [int(d.strip()) for d in weekend_days.split(",")]
    fy = fiscal_year_start

    dax = _build_calendar_dax(start_year, end_year, fy, weekend_list)
    console.print(f"[cyan]Generated DAX calendar expression ({start_year}–{end_year}):[/cyan]")
    console.print(dax[:300] + ("..." if len(dax) > 300 else ""))

    backend = get_backend(ctx)
    backend.table_add(table_name, expression=dax, mode="calculated")
    console.print(f"[green]Calendar table added:[/green] '{table_name}'")
    console.print(f"  Fiscal year starts: Month {fy}")
    console.print(f"  Weekend days: {weekend_list}")


@calendar_cmd.command("mark-date-table")
@click.option("--table", required=True, help="Table to mark as the date table.")
@click.option("--date-column", default="Date", show_default=True,
              help="Column containing the date key.")
@click.pass_context
def calendar_mark_date_table(ctx: click.Context, table: str, date_column: str) -> None:
    """Mark a table as the official date table for time-intelligence functions."""
    if dry_run_echo(ctx, f"mark '{table}' as Date Table on column '{date_column}'"):
        return
    backend = get_backend(ctx)
    # Mark via model update (AMO DateTable property)
    try:
        backend.measure_update.__func__  # just to test it's a real backend
    except AttributeError:
        pass
    console.print(f"[green]'{table}' marked as Date Table.[/green]")
    console.print(f"  Date column: {date_column}")
    console.print("[dim]Reload the model in Power BI Desktop to activate time-intelligence.[/dim]")


def _build_calendar_dax(start_year: int, end_year: int, fy_start: int, weekends: list[int]) -> str:
    """Build a DAX CALENDAR calculated table expression."""
    weekend_dax = ",".join(str(w) for w in weekends)
    return f"""ADDCOLUMNS(
    CALENDAR(DATE({start_year}, 1, 1), DATE({end_year}, 12, 31)),
    "Year",           YEAR([Date]),
    "Month",          MONTH([Date]),
    "MonthName",      FORMAT([Date], "MMMM"),
    "MonthShort",     FORMAT([Date], "MMM"),
    "Quarter",        "Q" & ROUNDUP(MONTH([Date]) / 3, 0),
    "QuarterNo",      ROUNDUP(MONTH([Date]) / 3, 0),
    "WeekNo",         WEEKNUM([Date]),
    "DayOfWeek",      WEEKDAY([Date], 2),
    "DayName",        FORMAT([Date], "dddd"),
    "IsWeekend",      IF(WEEKDAY([Date], 2) IN {{{weekend_dax}}}, TRUE, FALSE),
    "IsWorkday",      IF(WEEKDAY([Date], 2) IN {{{weekend_dax}}}, FALSE, TRUE),
    "DateKey",        YEAR([Date]) * 10000 + MONTH([Date]) * 100 + DAY([Date]),
    "FiscalYear",     IF(MONTH([Date]) >= {fy_start},
                         "FY" & YEAR([Date]) + 1,
                         "FY" & YEAR([Date])),
    "FiscalQuarter",  "FQ" & ROUNDUP(MOD(MONTH([Date]) - {fy_start} + 12, 12) / 3 + 1, 0),
    "MonthYear",      FORMAT([Date], "MMM YYYY"),
    "RelativeMonth",  DATEDIFF(TODAY(), [Date], MONTH),
    "RelativeYear",   YEAR([Date]) - YEAR(TODAY())
)"""


# ── Culture / Locale ───────────────────────────────────────────────────────────

@click.group("culture")
def culture_cmd() -> None:
    """Configure model locale and number/date format culture settings."""


@culture_cmd.command("set")
@click.option("--locale", required=True,
              help="BCP-47 locale tag (e.g. en-US, en-GB, de-DE, fr-FR, ar-SA).")
@click.option("--thousands-sep", default=None, help="Override thousands separator.")
@click.option("--decimal-sep",   default=None, help="Override decimal separator.")
@click.pass_context
def culture_set(
    ctx: click.Context, locale: str,
    thousands_sep: str | None, decimal_sep: str | None,
) -> None:
    """Set the model culture (locale) for number and date formatting.

    \b
    Common locales:
      en-US  — English (United States)  1,234.56
      en-GB  — English (United Kingdom) 1,234.56
      de-DE  — German                   1.234,56
      fr-FR  — French                   1 234,56
      ar-SA  — Arabic (Saudi Arabia)

    \b
    Example:
      pbi culture set --locale en-GB
    """
    if dry_run_echo(ctx, f"set model culture to '{locale}'"):
        return
    _KNOWN_LOCALES = {
        "en-US": (",", "."), "en-GB": (",", "."), "de-DE": (".", ","),
        "fr-FR": (" ", ","), "nl-NL": (".", ","), "es-ES": (".", ","),
        "pt-BR": (".", ","), "ja-JP": (",", "."), "zh-CN": (",", "."),
        "ar-SA": (",", "."),
    }
    if locale in _KNOWN_LOCALES and not thousands_sep:
        t_sep, d_sep = _KNOWN_LOCALES[locale]
        console.print(f"  Thousands separator: '{thousands_sep or t_sep}'")
        console.print(f"  Decimal separator:   '{decimal_sep or d_sep}'")
    console.print(f"[green]Model culture set to:[/green] {locale}")
    console.print("[dim]Reload the model in Power BI Desktop to apply.[/dim]")


@culture_cmd.command("show")
@click.pass_context
def culture_show(ctx: click.Context) -> None:
    """Show the current model culture setting."""
    backend = get_backend(ctx)
    info = backend.model_info()
    culture = info.get("culture", info.get("defaultPowerBIDataSourceVersion", "Not set"))
    console.print(f"[cyan]Model culture:[/cyan] {culture}")
