import csv
from datetime import date

import pytest

from hr_analytics import (
    Employee,
    annual_turnover,
    generate_employees,
    monthly_metrics,
    validate_metrics,
    write_demo,
)


def test_turnover_uses_average_headcount_with_hand_checked_january():
    people = [
        Employee("E1", "Sales", "Cairo", date(2023, 1, 1), date(2024, 1, 20)),
        Employee("E2", "Sales", "Cairo", date(2024, 1, 10), None),
        Employee("E3", "Sales", "Cairo", date(2023, 1, 1), None),
    ]
    row = monthly_metrics(people, date(2024, 1, 1), date(2024, 1, 1))[0]
    assert (row.start_headcount, row.hires, row.separations, row.end_headcount) == (2, 1, 1, 2)
    assert row.avg_headcount == 2.0
    assert row.turnover_rate == 0.5


def test_seeded_data_is_reproducible_and_contains_no_personal_columns():
    people = generate_employees(seed=11)
    assert people == generate_employees(seed=11)
    assert len({person.employee_id for person in people}) == len(people)
    assert all(person.termination_date is None or person.termination_date >= person.hire_date for person in people)
    assert all(person.employee_id.startswith("E") for person in people)


def test_metrics_reconcile_and_tampering_is_rejected():
    from dataclasses import replace

    people = generate_employees(seed=11)
    rows = monthly_metrics(people, date(2024, 1, 1), date(2025, 12, 1))
    validate_metrics(people, rows)
    changed = [replace(rows[0], separations=rows[0].separations + 1), *rows[1:]]
    with pytest.raises(ValueError, match="reconcile"):
        validate_metrics(people, changed)


def test_missing_department_month_is_rejected():
    people = generate_employees(seed=11)
    rows = monthly_metrics(people, date(2024, 1, 1), date(2025, 12, 1))
    with pytest.raises(ValueError, match="Missing"):
        validate_metrics(people, rows[1:])


def test_annual_turnover_uses_mean_monthly_headcount_not_sum():
    people = [
        Employee("E1", "Sales", "Cairo", date(2023, 1, 1), date(2024, 1, 20)),
        Employee("E2", "Sales", "Cairo", date(2024, 1, 10), None),
        Employee("E3", "Sales", "Cairo", date(2023, 1, 1), None),
    ]
    rows = monthly_metrics(people, date(2024, 1, 1), date(2024, 12, 1))
    # One separation; mean monthly headcount is 2, so annual turnover is 50%.
    assert annual_turnover(rows, 2024) == 0.5


def test_demo_writes_auditable_csv_and_dashboard_preview(tmp_path):
    write_demo(tmp_path, seed=11)
    assert (tmp_path / "employees.csv").is_file()
    assert (tmp_path / "monthly_department_metrics.csv").is_file()
    assert (tmp_path / "dashboard-preview.png").is_file()
    assert (tmp_path / "dashboard-preview.html").is_file()
    with (tmp_path / "monthly_department_metrics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 24 * 4
    assert all(float(row["turnover_rate"]) >= 0 for row in rows)
