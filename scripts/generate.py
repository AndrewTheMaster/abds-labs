#!/usr/bin/env python3
"""Generates the Energosbyt lab 1 CSV datasets in data/ using only the standard library."""

from __future__ import annotations

import csv
import os
from datetime import date, timedelta

NUM_REALTY = 1000
READINGS_FROM = date(2023, 11, 1)
READINGS_TO = date(2026, 10, 31)
REPLACEMENT_FROM = date(2025, 6, 1)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

ADDRESSES = [
    "г. Москва, ул. Пушкина, д. 1",
    "г. Москва, ул. Ленина, д. 12",
    "г. Москва, ул. Гагарина, д. 7",
    "г. Москва, ул. Мира, д. 25",
    "г. Москва, ул. Победы, д. 3",
]

SURNAMES = [
    "Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов",
    "Попов", "Васильев", "Соколов", "Михайлов", "Новиков",
]
NAMES = [
    "Иван", "Пётр", "Алексей", "Сергей", "Андрей",
    "Дмитрий", "Максим", "Николай", "Владимир", "Егор",
]
PATRONYMICS = [
    "Иванович", "Петрович", "Алексеевич", "Сергеевич", "Андреевич",
    "Дмитриевич", "Максимович", "Николаевич", "Владимирович", "Егорович",
]

GAUGE_MODELS = [
    ("Меркурий 201", "Россия"),
    ("Энергомера CE101", "Россия"),
    ("Нева 103", "Россия"),
    ("Makel Maks", "Турция"),
    ("ABB B23", "Германия"),
]

# One tariff with three SCD 2 versions. The second starts on 2025-01-01,
# the current one starts on 2026-11-01 and stays open until 2099.
TARIFFS = [
    (1, "День–Ночь", 620, 310, date(2023, 1, 1), date(2025, 1, 1), "2023-01-01 00:00:00", "2023-01-01 00:00:00"),
    (1, "День–Ночь", 680, 340, date(2025, 1, 1), date(2026, 11, 1), "2025-01-01 00:00:00", "2025-01-01 00:00:00"),
    (1, "День–Ночь", 720, 360, date(2026, 11, 1), date(2099, 1, 1), "2026-11-01 00:00:00", "2026-11-01 00:00:00"),
]
TARIFF_VALID_TO = ["2025-01-01 00:00:00", "2026-11-01 00:00:00", "2099-01-01 00:00:00"]


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def month_starts(start: date, end: date):
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def tariff_for(day: date) -> tuple[int, int]:
    for _, _, day_price, night_price, valid_from, valid_to, _, _ in TARIFFS:
        if valid_from <= day < valid_to:
            return day_price, night_price
    raise ValueError(f"no tariff for {day}")


def fio(index: int) -> str:
    i = index - 1
    return f"{SURNAMES[i % len(SURNAMES)]} {NAMES[(i * 3) % len(NAMES)]} {PATRONYMICS[(i * 7) % len(PATRONYMICS)]}"


def phone(index: int) -> str:
    return f"+7900{index:07d}"


def gauge_for(realty_id: int, day: date) -> int:
    if realty_id % 10 == 0 and day >= REPLACEMENT_FROM:
        return 1000 + realty_id // 10
    return realty_id


def write_csv(name: str, header: list[str], rows) -> int:
    path = os.path.join(DATA_DIR, f"{name}.csv")
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def generate_realty():
    for i in range(1, NUM_REALTY + 1):
        is_nrcp = i % 10 == 0
        yield [
            i,
            ADDRESSES[(i - 1) % len(ADDRESSES)],
            25 + ((i * 17) % 120),
            "nrcp" if is_nrcp else "flat",
            "" if is_nrcp else str(100 + i),
            1 + ((i * 3) % 5) if not is_nrcp else 1,
            1 + ((i * 7) % 25),
            1 + ((i * 11) % 6),
            "2023-01-01 00:00:00",
        ]


def generate_gauges():
    for i in range(1, NUM_REALTY + 1):
        name, country = GAUGE_MODELS[(i - 1) % len(GAUGE_MODELS)]
        yield [i, name, country, "2023-01-01 00:00:00"]
    for realty_id in range(10, NUM_REALTY + 1, 10):
        gauge_id = 1000 + realty_id // 10
        name, country = GAUGE_MODELS[(gauge_id - 1) % len(GAUGE_MODELS)]
        yield [gauge_id, name, country, "2025-06-01 00:00:00"]


def generate_tariffs():
    for index, (tariff_id, name, day_price, night_price, _, _, created_at, updated_at) in enumerate(TARIFFS):
        yield [
            tariff_id,
            name,
            day_price,
            night_price,
            created_at,
            TARIFF_VALID_TO[index],
            created_at,
            updated_at,
        ]


def generate_users():
    for i in range(1, NUM_REALTY + 1):
        yield [
            i,
            fio(i),
            phone(i),
            "",
            "2023-01-01 00:00:00",
            "2023-01-01 00:00:00",
        ]


def generate_bindings():
    for i in range(1, NUM_REALTY + 1):
        yield [i, i, "2023-11-01 00:00:00", 1, 1]
    for realty_id in range(10, NUM_REALTY + 1, 10):
        new_gauge = 1000 + realty_id // 10
        yield [realty_id, realty_id, "2025-06-01 00:00:00", -1, 1]
        yield [new_gauge, realty_id, "2025-06-01 00:00:01", 1, 2]


def iter_readings(monthly, months, days, stats):
    month_index = {month: index for index, month in enumerate(months)}
    day_month = [month_index[date(day.year, day.month, 1)] for day in days]
    day_iso = [day.isoformat() for day in days]

    for realty_id in range(1, NUM_REALTY + 1):
        user_id = realty_id
        for di, reading_date in enumerate(days):
            month = day_month[di]
            gauge_id = gauge_for(realty_id, reading_date)
            day_kw = 5 + ((realty_id * 13 + di * 7) % 45)
            night_kw = 1 + ((realty_id * 5 + di * 3) % 18)

            yield [
                realty_id,
                user_id,
                1,
                gauge_id,
                day_iso[di],
                day_kw,
                night_kw,
                day_iso[di] + " 20:00:00",
            ]

            if ((realty_id * 37 + di * 17) % 100) < 3:
                corrected_day = day_kw + 10 + (realty_id % 7)
                corrected_night = night_kw + 3 + (realty_id % 5)
                correction_date = (reading_date + timedelta(days=1)).isoformat()
                yield [
                    realty_id,
                    user_id,
                    1,
                    gauge_id,
                    day_iso[di],
                    corrected_day,
                    corrected_night,
                    correction_date + " 10:00:00",
                ]
                monthly[realty_id][month][0] += corrected_day
                monthly[realty_id][month][1] += corrected_night
                stats["corrections"] += 1
            else:
                monthly[realty_id][month][0] += day_kw
                monthly[realty_id][month][1] += night_kw


def generate_invoices(monthly, months):
    for realty_id in range(1, NUM_REALTY + 1):
        user_id = realty_id
        for index, month in enumerate(months):
            created_day = date(month.year, month.month, 27)
            day_kw, night_kw = monthly[realty_id][index]
            day_price, night_price = tariff_for(created_day)
            price = day_kw * day_price + night_kw * night_price
            deadline_month = next_month(month)
            deadline = date(deadline_month.year, deadline_month.month, 10)
            yield [
                realty_id,
                user_id,
                1,
                gauge_for(realty_id, created_day),
                day_kw,
                night_kw,
                price,
                deadline.isoformat(),
                created_day.isoformat() + " 10:00:00",
            ]


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    realties = write_csv("dim_realty", [
        "id", "address", "square", "type", "number", "rooms", "floor", "porch", "created_at",
    ], generate_realty())
    gauges = write_csv("dim_gauges", [
        "id", "name", "country", "created_at",
    ], generate_gauges())
    tariffs = write_csv("dim_tariffs", [
        "id", "name", "price_day_kwph", "price_night_kwph", "valid_from", "valid_to", "created_at", "updated_at",
    ], generate_tariffs())
    users = write_csv("dim_users", [
        "id", "fio", "phone", "phone_prev", "created_at", "updated_at",
    ], generate_users())
    bindings = write_csv("fact_gauge_bindings", [
        "gauge_id", "realty_id", "created_at", "sign", "version",
    ], generate_bindings())

    days = list(date_range(READINGS_FROM, READINGS_TO))
    months = list(month_starts(READINGS_FROM, READINGS_TO))
    monthly = [[[0, 0] for _ in months] for _ in range(NUM_REALTY + 1)]
    stats = {"corrections": 0}
    readings = write_csv("fact_meter_readings", [
        "realty_id", "user_id", "tariff_id", "gauge_id", "reading_date", "day_kw", "night_kw", "created_at",
    ], iter_readings(monthly, months, days, stats))

    invoices = write_csv("fact_invoice", [
        "realty_id", "user_id", "tariff_id", "gauge_id", "day_kw", "night_kw", "price", "deadline", "created_at",
    ], generate_invoices(monthly, months))

    print(f"dim_realty: {realties}")
    print(f"dim_gauges: {gauges}")
    print(f"dim_tariffs: {tariffs}")
    print(f"dim_users: {users}")
    print(f"fact_gauge_bindings: {bindings}")
    print(f"fact_meter_readings: {readings} physical rows, {readings - stats['corrections']} FINAL rows, {stats['corrections']} corrections")
    print(f"fact_invoice: {invoices}")
    print(f"CSV files written to {DATA_DIR}")


if __name__ == "__main__":
    main()
