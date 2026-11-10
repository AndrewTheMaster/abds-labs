# Сценарии SCD и SQL-проверки

## 1. Собственник сменил фамилию (SCD 1)

```sh
curl -i -X PATCH http://localhost:8080/users/1 \
  -H 'Content-Type: application/json' \
  -d '{"fio":"Петрова Анна Сергеевна"}'
curl http://localhost:8080/users/1
```

Ожидается `204`, затем новое ФИО в ответе. Старое значение не хранится в
актуальной версии:

```sql
SELECT id, fio, phone, phone_prev
FROM energosbyt.dim_users FINAL
WHERE id = 1;
```

При изменении ФИО сервис синхронно обновляет все физические версии строки,
а затем вставляет актуальную версию с новым `updated_at`. Поэтому старого
ФИО нет и в результате запроса без `FINAL`.

## 2. Собственник сменил телефон дважды (SCD 3)

```sh
curl -X PATCH http://localhost:8080/users/1 \
  -H 'Content-Type: application/json' -d '{"phone":"+79111111111"}'
curl -X PATCH http://localhost:8080/users/1 \
  -H 'Content-Type: application/json' -d '{"phone":"+79222222222"}'
curl http://localhost:8080/users/1
```

В ответе `phone` — последний телефон, `phone_prev` — предыдущий:

```sql
SELECT id, phone, phone_prev
FROM energosbyt.dim_users FINAL
WHERE id = 1;
```

## 3. Изменился тариф с 1 ноября (SCD 2)

До и после границы возвращаются разные версии:

```sh
curl 'http://localhost:8080/tariffs?date=2026-10-31'
curl 'http://localhost:8080/tariffs?date=2026-11-01'
```

SQL показывает все версии одного тарифа:

```sql
SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to
FROM energosbyt.dim_tariffs FINAL
WHERE id = 1
ORDER BY valid_from;
```

Проверка, что версия выбирается по правилу `valid_from <= date < valid_to`:

```sql
SELECT id, name, valid_from, valid_to
FROM energosbyt.dim_tariffs FINAL
WHERE id = 1
  AND valid_from <= toDateTime('2026-11-01 00:00:00')
  AND valid_to > toDateTime('2026-11-01 00:00:00');
```

## 4. Пересчёт счёта за старый месяц (SCD 2)

Счета лежат в `MergeTree` и не перезаписываются. Цена считается по версии
тарифа, действовавшей на `created_at` счёта. Сверка со старым счётом:

```sql
SELECT
    i.created_at,
    i.day_kw,
    i.night_kw,
    i.price,
    t.price_day_kwph * i.day_kw + t.price_night_kwph * i.night_kw AS price_check,
    t.valid_from,
    t.valid_to
FROM energosbyt.fact_invoice AS i
LEFT JOIN (
    SELECT id, price_day_kwph, price_night_kwph, valid_from, valid_to
    FROM energosbyt.dim_tariffs FINAL
) AS t
    ON i.tariff_id = t.id
   AND i.created_at >= t.valid_from
   AND i.created_at < t.valid_to
WHERE i.realty_id = 1
ORDER BY i.created_at;
```

`price` и `price_check` совпадают для каждой строки. Добавление новой версии
тарифа на будущие даты не меняет уже выставленные счета.

## 5. Корректировка показания (ReplacingMergeTree)

Передадим показание за `2026-10-01` дважды:

```sh
curl -i -X POST http://localhost:8080/realty/1/readings \
  -H 'Content-Type: application/json' \
  -d '{"user_id":1,"gauge_id":1,"tariff_id":1,"reading_date":"2026-10-01","day_kw":100,"night_kw":20}'
curl -i -X POST http://localhost:8080/realty/1/readings \
  -H 'Content-Type: application/json' \
  -d '{"user_id":1,"gauge_id":1,"tariff_id":1,"reading_date":"2026-10-01","day_kw":1250,"night_kw":300}'
curl 'http://localhost:8080/realty/1/readings?date_from=2026-10-01&date_to=2026-10-01'
```

В ответе ровно одна строка с последними значениями. SQL:

```sql
SELECT realty_id, reading_date, day_kw, night_kw, created_at
FROM energosbyt.fact_meter_readings
WHERE realty_id = 1 AND reading_date = toDate('2026-10-01')
ORDER BY created_at;

SELECT realty_id, reading_date, day_kw, night_kw, created_at
FROM energosbyt.fact_meter_readings FINAL
WHERE realty_id = 1 AND reading_date = toDate('2026-10-01');
```

Первый запрос может показать несколько физических строк, второй — одну
актуальную.

## 6. Замена счётчика (VersionedCollapsingMergeTree)

```sh
curl -i -X POST http://localhost:8080/realty/1/gauges \
  -H 'Content-Type: application/json' -d '{"gauge_id":2}'
```

Эндпоинт аннулирует активную установку строкой `sign = -1` с тем же
`version`, затем вставляет установку `gauge_id` с `sign = 1` и `version + 1`.
Физическая история:

```sql
SELECT realty_id, gauge_id, created_at, sign, version
FROM energosbyt.fact_gauge_bindings
WHERE realty_id = 1
ORDER BY version, sign;
```

Активная установка после `FINAL` — ровно одна:

```sql
SELECT realty_id, gauge_id, version
FROM energosbyt.fact_gauge_bindings FINAL
WHERE realty_id = 1 AND sign = 1;
```

## 7. Удаление ошибочной строки с лишним нулём (DELETE)

Вставим заведомо ошибочное показание, найдём его и удалим:

```sql
INSERT INTO energosbyt.fact_meter_readings
    (realty_id, user_id, tariff_id, gauge_id, reading_date, day_kw, night_kw, created_at)
VALUES
    (1, 1, 1, 1, toDate('2026-10-31'), 999999, 0, toDateTime('2026-10-31 23:00:00'));

SELECT count() FROM energosbyt.fact_meter_readings WHERE day_kw = 999999;

ALTER TABLE energosbyt.fact_meter_readings
    DELETE WHERE day_kw = 999999
    SETTINGS mutations_sync = 1;

SELECT count() FROM energosbyt.fact_meter_readings WHERE day_kw = 999999;
```

Последний запрос возвращает `0`: ошибочной строки больше нет.
