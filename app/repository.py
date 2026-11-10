"""SQL queries for the Energosbyt tables."""

import os


class EnergosbytRepository:
    def __init__(self, client):
        self.client = client
        self.database = os.environ["CLICKHOUSE_DATABASE"]

    def _one(self, query):
        rows = self.client.rows(query)
        return rows[0] if rows else None

    def realty_exists(self, realty_id):
        return int(self.client.scalar(
            f"SELECT count() AS c FROM {self.database}.dim_realty WHERE id = {realty_id}"
        )) > 0

    def get_realty(self, realty_id):
        return self._one(
            f"SELECT id, address, square, type, number, rooms, floor, porch "
            f"FROM {self.database}.dim_realty WHERE id = {realty_id} LIMIT 1"
        )

    def user_exists(self, user_id):
        return int(self.client.scalar(
            f"SELECT count() AS c FROM {self.database}.dim_users FINAL WHERE id = {user_id}"
        )) > 0

    def get_user(self, user_id):
        return self._one(
            f"SELECT id, fio, phone, phone_prev, created_at, updated_at "
            f"FROM {self.database}.dim_users FINAL WHERE id = {user_id} LIMIT 1"
        )

    def save_user(self, user_id, row, old_fio):
        if row["fio"] != old_fio:
            # SCD 1 also removes the old name from physical versions.
            encoded_fio = row["fio"].encode("utf-8").hex()
            self.client.execute(
                f"ALTER TABLE {self.database}.dim_users UPDATE fio = unhex('{encoded_fio}') "
                f"WHERE id = {user_id} SETTINGS mutations_sync = 1"
            )
        self.client.insert(f"INSERT INTO {self.database}.dim_users FORMAT JSONEachRow", [row])

    def gauge_exists(self, gauge_id):
        return int(self.client.scalar(
            f"SELECT count() AS c FROM {self.database}.dim_gauges WHERE id = {gauge_id}"
        )) > 0

    def tariff_exists(self, tariff_id):
        return int(self.client.scalar(
            f"SELECT count() AS c FROM {self.database}.dim_tariffs FINAL WHERE id = {tariff_id}"
        )) > 0

    def tariff_for_date(self, timestamp):
        return self._one(
            f"SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to "
            f"FROM {self.database}.dim_tariffs FINAL "
            f"WHERE valid_from <= toDateTime('{timestamp}') "
            f"AND valid_to > toDateTime('{timestamp}') ORDER BY id LIMIT 1"
        )

    def latest_reading_created_at(self, realty_id, day):
        row = self._one(
            f"SELECT max(created_at) AS m FROM {self.database}.fact_meter_readings "
            f"WHERE realty_id = {realty_id} AND reading_date = toDate('{day}')"
        )
        return row["m"] if row else None

    def insert_reading(self, row):
        self.client.insert(
            f"INSERT INTO {self.database}.fact_meter_readings FORMAT JSONEachRow", [row]
        )

    def list_readings(self, realty_id, date_from, date_to):
        return self.client.rows(
            f"SELECT user_id, tariff_id, gauge_id, reading_date, day_kw, night_kw "
            f"FROM {self.database}.fact_meter_readings FINAL "
            f"WHERE realty_id = {realty_id} "
            f"AND reading_date >= toDate('{date_from}') "
            f"AND reading_date <= toDate('{date_to}') ORDER BY reading_date"
        )

    def count_invoices(self, realty_id):
        return int(self.client.scalar(
            f"SELECT count() AS c FROM {self.database}.fact_invoice WHERE realty_id = {realty_id}"
        ))

    def list_invoices(self, realty_id, limit, offset):
        return self.client.rows(
            f"SELECT tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at "
            f"FROM {self.database}.fact_invoice WHERE realty_id = {realty_id} "
            f"ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"
        )

    def active_binding(self, realty_id):
        return self._one(
            f"SELECT gauge_id, version FROM {self.database}.fact_gauge_bindings FINAL "
            f"WHERE realty_id = {realty_id} AND sign = 1 "
            f"ORDER BY version DESC LIMIT 1"
        )

    def insert_bindings(self, rows):
        self.client.insert(
            f"INSERT INTO {self.database}.fact_gauge_bindings FORMAT JSONEachRow", rows
        )
