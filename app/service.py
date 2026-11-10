"""Validation and SCD behavior independent of HTTP and SQL transport."""

import re
from datetime import datetime, timedelta

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class BadRequest(Exception):
    pass


class NotFound(Exception):
    pass


def is_uint(value, minimum=0, maximum=(1 << 64) - 1):
    return (isinstance(value, int) and not isinstance(value, bool)
            and minimum <= value <= maximum)


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        return None


def parse_datetime(value):
    try:
        return datetime.strptime(value, DATETIME_FORMAT)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1)


def require_field(body, field, minimum=0, maximum=(1 << 64) - 1):
    if field not in body or not is_uint(body[field], minimum, maximum):
        raise BadRequest(f'invalid "{field}" field')
    return body[field]


def require_realty(repository, realty_id):
    if not repository.realty_exists(realty_id):
        raise NotFound()


class EnergosbytService:
    def __init__(self, repository):
        self.repository = repository

    def get_user(self, user_id):
        row = self.repository.get_user(user_id)
        if row is None:
            raise NotFound()
        return {"id": int(row["id"]), "fio": row["fio"],
                "phone": row["phone"], "phone_prev": row["phone_prev"]}

    def patch_user(self, user_id, body):
        if body is None:
            raise BadRequest("invalid request body")
        has_fio, has_phone = "fio" in body, "phone" in body
        if has_fio and (not isinstance(body["fio"], str) or not body["fio"].strip()):
            raise BadRequest('invalid "fio" field')
        if has_phone and (not isinstance(body["phone"], str) or not body["phone"].strip()):
            raise BadRequest('invalid "phone" field')
        if not has_fio and not has_phone:
            raise BadRequest("at least one field is required")
        current = self.repository.get_user(user_id)
        if current is None:
            raise NotFound()

        new_phone = body["phone"] if has_phone else current["phone"]
        previous_phone = current["phone_prev"]
        if new_phone != current["phone"]:
            previous_phone = current["phone"]
        updated_at = datetime.utcnow().replace(microsecond=0)
        old_updated_at = parse_datetime(current["updated_at"])
        if updated_at <= old_updated_at:
            updated_at = old_updated_at + timedelta(seconds=1)
        self.repository.save_user(user_id, {
            "id": user_id,
            "fio": body["fio"] if has_fio else current["fio"],
            "phone": new_phone,
            "phone_prev": previous_phone,
            "created_at": current["created_at"],
            "updated_at": updated_at.strftime(DATETIME_FORMAT),
        }, current["fio"])

    def get_realty(self, realty_id):
        row = self.repository.get_realty(realty_id)
        if row is None:
            raise NotFound()
        return {"id": int(row["id"]), "address": row["address"],
                "square": int(row["square"]), "type": row["type"],
                "number": row["number"], "rooms": int(row["rooms"]),
                "floor": int(row["floor"]), "porch": int(row["porch"])}

    def post_reading(self, realty_id, body):
        if body is None:
            raise BadRequest("invalid request body")
        user_id = require_field(body, "user_id", 1)
        gauge_id = require_field(body, "gauge_id", 1)
        tariff_id = require_field(body, "tariff_id", 1)
        reading_date = parse_date(body.get("reading_date"))
        if reading_date is None:
            raise BadRequest('invalid "reading_date" field')
        day_kw = require_field(body, "day_kw", 0, (1 << 32) - 1)
        night_kw = require_field(body, "night_kw", 0, (1 << 32) - 1)
        require_realty(self.repository, realty_id)
        if not (self.repository.user_exists(user_id)
                and self.repository.gauge_exists(gauge_id)
                and self.repository.tariff_exists(tariff_id)):
            raise NotFound()

        day = reading_date.isoformat()
        created_at = datetime.utcnow().replace(microsecond=0)
        latest = parse_datetime(self.repository.latest_reading_created_at(realty_id, day))
        if created_at <= latest:
            created_at = latest + timedelta(seconds=1)
        self.repository.insert_reading({
            "realty_id": realty_id, "user_id": user_id, "tariff_id": tariff_id,
            "gauge_id": gauge_id, "reading_date": day,
            "day_kw": day_kw, "night_kw": night_kw,
            "created_at": created_at.strftime(DATETIME_FORMAT),
        })

    def get_readings(self, realty_id, params):
        date_from = parse_date(params.get("date_from", [None])[0])
        date_to = parse_date(params.get("date_to", [None])[0])
        if date_from is None:
            raise BadRequest('invalid "date_from" parameter')
        if date_to is None:
            raise BadRequest('invalid "date_to" parameter')
        if date_from > date_to:
            raise BadRequest('invalid "date_from" parameter')
        require_realty(self.repository, realty_id)
        rows = self.repository.list_readings(
            realty_id, date_from.isoformat(), date_to.isoformat()
        )
        readings = [{
            "reading_date": row["reading_date"], "user_id": int(row["user_id"]),
            "tariff_id": int(row["tariff_id"]), "gauge_id": int(row["gauge_id"]),
            "day_kw": int(row["day_kw"]), "night_kw": int(row["night_kw"]),
        } for row in rows]
        return {"readings": readings, "count": len(readings)}

    def get_invoices(self, realty_id, params):
        values = {}
        for name, default in (("limit", 10), ("offset", 0)):
            if name not in params:
                values[name] = default
                continue
            raw = params[name][0]
            if not re.fullmatch(r"\d+", raw or ""):
                raise BadRequest(f'invalid "{name}" parameter')
            values[name] = int(raw)
        require_realty(self.repository, realty_id)
        count = self.repository.count_invoices(realty_id)
        rows = self.repository.list_invoices(realty_id, values["limit"], values["offset"])
        invoices = [{
            "tariff_id": int(row["tariff_id"]), "gauge_id": int(row["gauge_id"]),
            "day_kw": int(row["day_kw"]), "night_kw": int(row["night_kw"]),
            "price": int(row["price"]), "deadline": row["deadline"],
            "created_at": row["created_at"],
        } for row in rows]
        return {"invoices": invoices, "count": count}

    def get_tariff(self, params):
        day = parse_date(params.get("date", [None])[0])
        if day is None:
            raise BadRequest('invalid "date" parameter')
        row = self.repository.tariff_for_date(day.isoformat() + " 00:00:00")
        if row is None:
            raise NotFound()
        return {"id": int(row["id"]), "name": row["name"],
                "price_day_kwph": int(row["price_day_kwph"]),
                "price_night_kwph": int(row["price_night_kwph"]),
                "valid_from": row["valid_from"], "valid_to": row["valid_to"]}

    def post_gauge(self, realty_id, body):
        if body is None:
            raise BadRequest("invalid request body")
        gauge_id = require_field(body, "gauge_id", 1)
        require_realty(self.repository, realty_id)
        if not self.repository.gauge_exists(gauge_id):
            raise NotFound()
        active = self.repository.active_binding(realty_id)
        created_at = datetime.utcnow().replace(microsecond=0).strftime(DATETIME_FORMAT)
        rows = []
        version = 1
        if active is not None:
            version = int(active["version"]) + 1
            rows.append({
                "gauge_id": int(active["gauge_id"]), "realty_id": realty_id,
                "created_at": created_at, "sign": -1, "version": version - 1,
            })
        rows.append({
            "gauge_id": gauge_id, "realty_id": realty_id,
            "created_at": created_at, "sign": 1, "version": version,
        })
        self.repository.insert_bindings(rows)
