"""Generate and reconcile a synthetic HR attrition dataset and dashboard preview."""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEPARTMENTS = ("Engineering", "Sales", "Operations", "Finance")
LOCATIONS = ("Cairo", "Alexandria", "Giza")


@dataclass(frozen=True)
class Employee:
    employee_id: str
    department: str
    location: str
    hire_date: date
    termination_date: date | None


@dataclass(frozen=True)
class MonthlyMetric:
    month: date
    department: str
    start_headcount: int
    hires: int
    separations: int
    end_headcount: int
    avg_headcount: float
    turnover_rate: float


def next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def months_between(first: date, last: date):
    month = first
    while month <= last:
        yield month
        month = next_month(month)


def generate_employees(seed: int = 42) -> list[Employee]:
    """Create fictional employee IDs and lifecycle dates with a fixed seed."""
    rng = random.Random(seed)
    people: list[Employee] = []
    next_id = 1
    for department in DEPARTMENTS:
        for _ in range(48):
            people.append(Employee(
                f"E{next_id:04d}", department, rng.choice(LOCATIONS),
                date(rng.randint(2019, 2023), rng.randint(1, 12), rng.randint(1, 25)), None,
            ))
            next_id += 1

    for month in months_between(date(2024, 1, 1), date(2025, 12, 1)):
        for department in DEPARTMENTS:
            active = [
                index for index, person in enumerate(people)
                if person.department == department
                and person.hire_date < month
                and person.termination_date is None
            ]
            exit_count = rng.randint(1, 3) + (department == "Sales" and rng.randint(0, 1))
            for index in rng.sample(active, min(exit_count, len(active))):
                person = people[index]
                people[index] = Employee(
                    person.employee_id, person.department, person.location,
                    person.hire_date, date(month.year, month.month, rng.randint(8, 26)),
                )
            for _ in range(rng.randint(2, 5)):
                people.append(Employee(
                    f"E{next_id:04d}", department, rng.choice(LOCATIONS),
                    date(month.year, month.month, rng.randint(1, 25)), None,
                ))
                next_id += 1
    return people


def monthly_metrics(people: list[Employee], first: date, last: date) -> list[MonthlyMetric]:
    if first.day != 1 or last.day != 1 or first > last:
        raise ValueError("Date range must use ordered first days of months")
    rows: list[MonthlyMetric] = []
    for month in months_between(first, last):
        following = next_month(month)
        for department in sorted({person.department for person in people}):
            group = [person for person in people if person.department == department]
            start_count = sum(
                person.hire_date < month
                and (person.termination_date is None or person.termination_date >= month)
                for person in group
            )
            hires = sum(month <= person.hire_date < following for person in group)
            separations = sum(
                person.termination_date is not None
                and month <= person.termination_date < following
                for person in group
            )
            end_count = sum(
                person.hire_date < following
                and (person.termination_date is None or person.termination_date >= following)
                for person in group
            )
            average = (start_count + end_count) / 2
            rows.append(MonthlyMetric(
                month, department, start_count, hires, separations, end_count,
                average, separations / average if average else 0.0,
            ))
    return rows


def validate_metrics(people: list[Employee], rows: list[MonthlyMetric]) -> None:
    """Check ledger-to-mart reconciliation, period continuity, and rate arithmetic."""
    if not rows:
        raise ValueError("Missing monthly metrics")
    if len({person.employee_id for person in people}) != len(people):
        raise ValueError("Duplicate employee IDs")
    if any(
        person.termination_date is not None and person.termination_date < person.hire_date
        for person in people
    ):
        raise ValueError("Termination precedes hire date")
    departments = {person.department for person in people}
    expected_keys = {
        (month, department)
        for month in months_between(min(row.month for row in rows), max(row.month for row in rows))
        for department in departments
    }
    actual_keys = {(row.month, row.department) for row in rows}
    if expected_keys - actual_keys:
        raise ValueError("Missing month-department metric")
    if actual_keys - expected_keys:
        raise ValueError("Unknown department in monthly metrics")
    seen: set[tuple[date, str]] = set()
    prior_end: dict[str, int] = {}
    for row in sorted(rows, key=lambda item: (item.month, item.department)):
        key = (row.month, row.department)
        if key in seen:
            raise ValueError("Duplicate month-department metric")
        seen.add(key)
        following = next_month(row.month)
        group = [person for person in people if person.department == row.department]
        ledger_start = sum(
            person.hire_date < row.month
            and (person.termination_date is None or person.termination_date >= row.month)
            for person in group
        )
        ledger_hires = sum(row.month <= person.hire_date < following for person in group)
        ledger_exits = sum(
            person.termination_date is not None
            and row.month <= person.termination_date < following
            for person in group
        )
        ledger_end = sum(
            person.hire_date < following
            and (person.termination_date is None or person.termination_date >= following)
            for person in group
        )
        if (
            (row.start_headcount, row.hires, row.separations, row.end_headcount)
            != (ledger_start, ledger_hires, ledger_exits, ledger_end)
            or row.end_headcount != row.start_headcount + row.hires - row.separations
            or row.avg_headcount != (row.start_headcount + row.end_headcount) / 2
            or abs(row.turnover_rate - (row.separations / row.avg_headcount if row.avg_headcount else 0)) > 1e-12
        ):
            raise ValueError(f"Metrics do not reconcile for {row.month} / {row.department}")
        if row.department in prior_end and prior_end[row.department] != row.start_headcount:
            raise ValueError(f"Headcount does not reconcile across months for {row.department}")
        prior_end[row.department] = row.end_headcount


def annual_turnover(rows: list[MonthlyMetric], year: int, department: str | None = None) -> float:
    chosen = [
        row for row in rows if row.month.year == year
        and (department is None or row.department == department)
    ]
    periods = sorted({row.month for row in chosen})
    if len(periods) != 12:
        raise ValueError(f"Expected 12 months of metrics for {year}")
    monthly_average = [
        sum(row.avg_headcount for row in chosen if row.month == month)
        for month in periods
    ]
    denominator = sum(monthly_average) / 12
    return sum(row.separations for row in chosen) / denominator if denominator else 0.0


def render_png(rows: list[MonthlyMetric], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    months = sorted({row.month for row in rows})
    headcount = [sum(row.end_headcount for row in rows if row.month == month) for month in months]
    exits = [sum(row.separations for row in rows if row.month == month) for month in months]
    monthly_avg = [sum(row.avg_headcount for row in rows if row.month == month) for month in months]
    monthly_rate = [100 * exit_count / average if average else 0 for exit_count, average in zip(exits, monthly_avg)]
    latest_year = months[-1].year
    current = [row for row in rows if row.month.year == latest_year]
    department_rates = {
        department: 100 * annual_turnover(rows, latest_year, department)
        for department in DEPARTMENTS
    }
    bg, panel, cyan, coral, muted = "#0d1726", "#152438", "#58d6dd", "#ff9278", "#9eb3c7"
    fig = plt.figure(figsize=(16, 9), facecolor=bg)
    fig.text(0.05, 0.93, "WORKFORCE  /  PULSE", fontsize=27, weight="bold", color="white")
    fig.text(0.05, 0.895, "Synthetic HR analytics • monthly movement and turnover", fontsize=12, color=muted)
    fig.text(0.95, 0.94, f"JAN 2024 — DEC {latest_year}", fontsize=10, color=cyan, ha="right", weight="bold")

    cards = [
        ("END HEADCOUNT", f"{headcount[-1]:,}", "as of Dec 31"),
        ("NEW HIRES", f"{sum(row.hires for row in current):,}", f"during {latest_year}"),
        ("SEPARATIONS", f"{sum(row.separations for row in current):,}", f"during {latest_year}"),
        ("ANNUAL TURNOVER", f"{100 * annual_turnover(rows, latest_year):.1f}%", "exits / mean monthly HC"),
    ]
    for index, (label, value, subline) in enumerate(cards):
        left = 0.05 + index * 0.235
        card = FancyBboxPatch(
            (left, 0.73), 0.22, 0.12, boxstyle="round,pad=0.009,rounding_size=0.012",
            transform=fig.transFigure, facecolor=panel, linewidth=0,
        )
        fig.add_artist(card)
        fig.text(left + 0.018, 0.817, label, fontsize=10, color=muted, weight="bold")
        fig.text(left + 0.018, 0.768, value, fontsize=25, color=cyan if index != 2 else coral, weight="bold")
        fig.text(left + 0.018, 0.741, subline, fontsize=9, color=muted)

    ax_head = fig.add_axes((0.06, 0.37, 0.57, 0.29), facecolor=panel)
    x = list(range(len(months)))
    ax_head.plot(x, headcount, color=cyan, lw=3, marker="o", markersize=4)
    ax_head.fill_between(x, headcount, min(headcount) - 8, color=cyan, alpha=0.08)
    ax_head.set_ylim(min(headcount) - 8, max(headcount) + 12)
    ax_head.set_title("HEADCOUNT TREND", color="white", fontsize=12, weight="bold", loc="left", pad=16)
    ax_head.set_xticks(x[::3], [months[index].strftime("%b %y") for index in x[::3]])
    ax_head.grid(axis="y", color="white", alpha=0.08)
    ax_head.annotate(str(headcount[-1]), (x[-1], headcount[-1]), xytext=(-10, 11), textcoords="offset points", color=cyan)

    ax_dept = fig.add_axes((0.69, 0.37, 0.25, 0.29), facecolor=panel)
    ranked = sorted(department_rates.items(), key=lambda item: item[1])
    ax_dept.barh([name for name, _ in ranked], [rate for _, rate in ranked], color=[cyan, "#4ba3bd", "#6587b0", coral])
    ax_dept.set_title(f"TURNOVER BY DEPARTMENT  /  {latest_year}", color="white", fontsize=11, weight="bold", loc="left", pad=16)
    ax_dept.set_xlim(0, max(department_rates.values()) * 1.25)
    for index, (_, rate) in enumerate(ranked):
        ax_dept.text(rate + 0.35, index, f"{rate:.1f}%", va="center", color="white", fontsize=10)
    ax_dept.set_xticks([])

    ax_rate = fig.add_axes((0.06, 0.105, 0.57, 0.18), facecolor=panel)
    ax_rate.bar(x, monthly_rate, color=coral, alpha=0.9)
    ax_rate.set_title("MONTHLY SEPARATION RATE", color="white", fontsize=12, weight="bold", loc="left", pad=13)
    ax_rate.set_xticks(x[::3], [months[index].strftime("%b %y") for index in x[::3]])
    ax_rate.set_ylabel("% of average HC", color=muted)
    ax_rate.grid(axis="y", color="white", alpha=0.08)

    fig.text(0.69, 0.265, "READ THE RATE CORRECTLY", fontsize=11, color=cyan, weight="bold")
    fig.text(
        0.69, 0.225,
        "Monthly: separations / average of\nstarting and ending headcount.\n"
        "Annual: total exits / mean of the\n12 monthly average headcounts.",
        fontsize=10, color=muted, linespacing=1.55, va="top",
    )
    fig.text(
        0.05, 0.035,
        "PORTFOLIO PREVIEW  •  Fictional IDs and generated dates  •  Tableau workbook pending native authoring",
        fontsize=9, color="#7289a0",
    )
    for axis in (ax_head, ax_dept, ax_rate):
        axis.tick_params(colors=muted, labelsize=9, length=0)
        for spine in axis.spines.values():
            spine.set_visible(False)
    fig.savefig(path, dpi=145, facecolor=bg)
    plt.close(fig)


def render_html(rows: list[MonthlyMetric], path: Path) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    months = sorted({row.month for row in rows})
    groups = ("All departments", *DEPARTMENTS)
    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
        subplot_titles=("Ending headcount", "Monthly separation rate"),
    )
    for group_index, group in enumerate(groups):
        chosen = rows if group == "All departments" else [row for row in rows if row.department == group]
        ending = [sum(row.end_headcount for row in chosen if row.month == month) for month in months]
        separations = [sum(row.separations for row in chosen if row.month == month) for month in months]
        average = [sum(row.avg_headcount for row in chosen if row.month == month) for month in months]
        rate = [100 * count / avg if avg else 0 for count, avg in zip(separations, average)]
        visible = group_index == 0
        figure.add_trace(go.Scatter(
            x=months, y=ending, mode="lines+markers", name="Headcount",
            line=dict(color="#58d6dd", width=3), visible=visible,
            hovertemplate="%{x|%b %Y}<br>%{y} employees<extra></extra>",
        ), row=1, col=1)
        figure.add_trace(go.Bar(
            x=months, y=rate, name="Separation rate",
            marker_color="#ff9278", visible=visible,
            hovertemplate="%{x|%b %Y}<br>%{y:.1f}%<extra></extra>",
        ), row=2, col=1)
    buttons = []
    for index, group in enumerate(groups):
        visibility = [item in (2 * index, 2 * index + 1) for item in range(2 * len(groups))]
        buttons.append(dict(
            label=group, method="update",
            args=[{"visible": visibility}, {"title": f"Workforce Pulse · {group}"}],
        ))
    figure.update_layout(
        title="Workforce Pulse · All departments", template="plotly_dark",
        paper_bgcolor="#0d1726", plot_bgcolor="#152438", font=dict(color="#dbe8f1"),
        width=1150, height=780, margin=dict(l=90, r=50, t=125, b=70),
        updatemenus=[dict(buttons=buttons, direction="down", x=1, xanchor="right", y=1.15, yanchor="top")],
        showlegend=False,
    )
    figure.update_yaxes(title_text="People", row=1, col=1)
    figure.update_yaxes(title_text="% of average HC", row=2, col=1)
    figure.write_html(path, include_plotlyjs=True, full_html=True)


def write_demo(output_dir: Path, seed: int = 42) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    people = generate_employees(seed)
    rows = monthly_metrics(people, date(2024, 1, 1), date(2025, 12, 1))
    validate_metrics(people, rows)
    with (output_dir / "employees.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("employee_id", "department", "location", "hire_date", "termination_date"))
        for person in people:
            writer.writerow((
                person.employee_id, person.department, person.location,
                person.hire_date.isoformat(),
                person.termination_date.isoformat() if person.termination_date else "",
            ))
    with (output_dir / "monthly_department_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "month", "department", "start_headcount", "hires", "separations",
            "end_headcount", "avg_headcount", "turnover_rate",
        ))
        for row in rows:
            writer.writerow((
                row.month.isoformat(), row.department, row.start_headcount, row.hires,
                row.separations, row.end_headcount,
                f"{row.avg_headcount:.1f}", f"{row.turnover_rate:.8f}",
            ))
    render_png(rows, output_dir / "dashboard-preview.png")
    render_html(rows, output_dir / "dashboard-preview.html")
    summary = {
        "seed": seed,
        "employees_generated": len(people),
        "monthly_department_rows": len(rows),
        "ending_headcount_2025": sum(row.end_headcount for row in rows if row.month == date(2025, 12, 1)),
        "separations_2025": sum(row.separations for row in rows if row.month.year == 2025),
        "annual_turnover_2025": round(annual_turnover(rows, 2025), 8),
        "reconciliation": "passed",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(write_demo(args.output_dir, args.seed), indent=2))


if __name__ == "__main__":
    main()
