# ЭнергоСбыт — лабораторная работа №1 (SCD в ClickHouse)

Backend-сервис вымышленной ЖКХ-компании «ЭнергоСбыт»: ClickHouse 26.7,
генератор CSV-датасетов и HTTP API на Python без внешних зависимостей.
Работа демонстрирует SCD 1, SCD 2 и SCD 3, а также удаление и аннулирование
данных в `MergeTree`, `ReplacingMergeTree` и
`VersionedCollapsingMergeTree`.

## Быстрый старт

```sh
make run
make setup
curl http://localhost:8080/ping
make teardown
make stop
```

`make run` поднимает ClickHouse и приложение через Docker Compose.
`make setup` создаёт схему, генерирует CSV в `data/` и загружает их в ClickHouse.
`make teardown` удаляет базу `energosbyt` со всеми таблицами и данными.

Проверка ClickHouse с хоста:

```sh
curl http://localhost:8123/ping
# Ok.
```

## Структура проекта

```text
.
├── app/main.py                 # HTTP API (стандартная библиотека Python)
├── scripts/generate.py         # генератор CSV-датасетов
├── scripts/ch.sh               # clickhouse-client внутри контейнера
├── scripts/load.sh             # идемпотентная загрузка CSV
├── sql/schema.sql              # схема energosbyt
├── sql/truncate.sql            # очистка таблиц перед загрузкой
├── sql/teardown.sql            # удаление базы
├── api/lab1.http               # коллекция запросов для ручной проверки API
├── docker-compose.yml          # ClickHouse 26.7 + приложение
├── Dockerfile                  # образ приложения
├── .env.local                  # единственный файл конфигурации
└── Makefile                    # run/stop/gen/load/setup/teardown
```

## Конфигурация

Все параметры берутся из `.env.local`. Файл коммитится в репозиторий,
секретов в нём нет.

| Переменная | Назначение |
| --- | --- |
| `APP_PORT` | порт HTTP-сервиса на хосте и внутри контейнера |
| `CLICKHOUSE_HOST` | адрес ClickHouse с хоста (`localhost`) |
| `CLICKHOUSE_PORT` | нативный порт ClickHouse с хоста (`9000`) |
| `CLICKHOUSE_HTTP_PORT` | HTTP-порт ClickHouse с хоста (`8123`) |
| `CLICKHOUSE_USER` | пользователь ClickHouse |
| `CLICKHOUSE_PASSWORD` | пароль ClickHouse, может быть пустым |
| `CLICKHOUSE_DATABASE` | база данных (`energosbyt`) |

Приложение ходит в ClickHouse по имени сервиса `clickhouse` и внутреннему
HTTP-порту контейнера `8123`. Наружу этот порт публикуется значением
`CLICKHOUSE_HTTP_PORT` из `.env.local`.

## Данные

`make gen` пишет CSV в `data/`. Папки `data/` и `volume/` добавлены в
`.gitignore`, датасеты и данные ClickHouse в git не попадают. Генератор
использует только стандартную библиотеку Python и укладывается в лимит CI.

| Таблица | Строк | Особенности |
| --- | --- | --- |
| `dim_realty` | 1 000 | квартиры и нежилые помещения, несколько домов |
| `dim_gauges` | 1 100 | по счётчику на объект + 100 заменённых счётчиков |
| `dim_tariffs` | 3 | один тариф с тремя версиями SCD 2, открытая до `2099-01-01` |
| `dim_users` | 1 000 | собственник на каждый объект |
| `fact_gauge_bindings` | 1 200 физически | 1 000 активных привязок после `FINAL`, 100 замен |
| `fact_meter_readings` | 1 096 000 после `FINAL` | каждый объект за каждый день с `2023-11-01` по `2026-10-31`; около 3% корректировок |
| `fact_invoice` | 36 000 | 36 месяцев на каждый объект, срок оплаты — 10-е число следующего месяца |

Показания за `2023-11-01`–`2026-10-31` — это 1 096 дней на 1 000 объектов.
Корректировка — дополнительная строка с тем же ключом
`(realty_id, reading_date)` и более поздним `created_at`; после `FINAL`
остаётся одно актуальное значение на дату.

Тариф имеет версии:

| `valid_from` | `valid_to` | День, коп. | Ночь, коп. |
| --- | --- | --- | --- |
| `2023-01-01 00:00:00` | `2025-01-01 00:00:00` | 620 | 310 |
| `2025-01-01 00:00:00` | `2026-11-01 00:00:00` | 680 | 340 |
| `2026-11-01 00:00:00` | `2099-01-01 00:00:00` | 720 | 360 |

### Загрузка и повторный запуск

`make load` сначала выполняет `TRUNCATE TABLE IF EXISTS` для всех семи таблиц,
затем загружает CSV через `clickhouse-client` с `FORMAT CSVWithNames`.
Поэтому повторный `make load` без предварительной очистки не создаёт дублей:
таблицы предварительно очищаются. `make setup` делает то же самое после
создания схемы.

## Схема и обоснование ключей и партиций

| Таблица | Движок | `ORDER BY` | Партиционирование |
| --- | --- | --- | --- |
| `dim_realty` | `MergeTree` | `id` | нет |
| `dim_gauges` | `MergeTree` | `id` | нет |
| `dim_tariffs` | `ReplacingMergeTree(updated_at)` | `(id, valid_from)` | нет |
| `dim_users` | `ReplacingMergeTree(updated_at)` | `id` | нет |
| `fact_gauge_bindings` | `VersionedCollapsingMergeTree(sign, version)` | `(realty_id, gauge_id)` | нет |
| `fact_meter_readings` | `ReplacingMergeTree(created_at)` | `(realty_id, reading_date)` | `toYYYYMM(reading_date)` |
| `fact_invoice` | `MergeTree` | `(realty_id, created_at)` | `toYYYYMM(created_at)` |

- `dim_realty`, `dim_gauges`, `dim_users` — небольшие измерения, точечные
  выборки по `id`, поэтому ключ `id` и отсутствие партиций оптимальны.
- `dim_tariffs` — SCD 2. В ключ входит `valid_from`, иначе `FINAL` схлопнул бы
  разные версии одного тарифа. `updated_at` задаёт версию строки для
  `ReplacingMergeTree`.
- `fact_gauge_bindings` — ключ `(realty_id, gauge_id)` позволяет аннулирующей
  строке с `sign = -1` иметь те же ключевые поля и `version`, что у установки.
  После `FINAL` остаётся ровно одна активная установка на объект. При замене
  счётчика старая строка аннулируется с тем же `version`, новая установка
  получает `version + 1`.
- `fact_meter_readings` — ключ `(realty_id, reading_date)` делает корректировку
  новой строкой с тем же ключом; `ReplacingMergeTree(created_at)` оставляет
  строку с максимальным `created_at`. Партиция по месяцу даёт отсечение
  партиций в запросах за период.
- `fact_invoice` — счета только добавляются, старые строки не меняются.
  Ключ `(realty_id, created_at)` соответствует сортировке API по `created_at`
  по убыванию; партиция по месяцу ускоряет выборки за период.

## HTTP API

Все ответы и тела запросов — JSON, ошибки — `{"message": "..."}`.
Даты — `YYYY-MM-DD`, даты со временем — `YYYY-MM-DD HH:MM:SS`.

| Метод и путь | Назначение |
| --- | --- |
| `GET /ping` | проверка доступности, `200` с пустым телом |
| `GET /users/{id}` | собственник |
| `PATCH /users/{id}` | SCD 1 для `fio`, SCD 3 для `phone` |
| `GET /realty/{id}` | объект недвижимости |
| `POST /realty/{id}/readings` | передача показания, повтор — корректировка |
| `GET /realty/{id}/readings?date_from=...&date_to=...` | актуальные показания за период |
| `GET /realty/{id}/invoices?limit=10&offset=0` | счета объекта с пагинацией |
| `GET /tariffs?date=YYYY-MM-DD` | версия тарифа, действующая на дату |
| `POST /realty/{id}/gauges` | установка/замена счётчика |

Примеры запросов для HTTP-клиента находятся в `api/lab1.http`.

Основные ошибки: `400` с сообщением `invalid "<поле>" field` или
`invalid "<параметр>" parameter`, `404` с сообщением `Not found`.
Успешные `PATCH`, `POST` и `GET /ping` возвращают пустое тело (`204`, `201`
или `200` соответственно).

Актуальные записи читаются с `FINAL`: так API не зависит от фонового слияния
`ReplacingMergeTree` и `VersionedCollapsingMergeTree`.

## Сценарии SCD и SQL-проверки

Ниже `ch` — это сокращение для запуска клиента внутри контейнера:

```sh
docker compose exec clickhouse clickhouse-client --query "SELECT ..."
```

### 1. Собственник сменил фамилию (SCD 1)

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

### 2. Собственник сменил телефон дважды (SCD 3)

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

### 3. Изменился тариф с 1 ноября (SCD 2)

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

### 4. Пересчёт счёта за старый месяц (SCD 2)

Счета лежат в `MergeTree` и не перезаписываются. Цена считается по версии
тарифа, действовавшей на `created_at` счёта. Старый счёт не меняется:

```sql
SELECT realty_id, tariff_id, day_kw, night_kw, price, deadline, created_at
FROM energosbyt.fact_invoice
WHERE realty_id = 1
ORDER BY created_at;
```

Сверка цены с версией тарифа на дату счёта:

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

### 5. Корректировка показания (ReplacingMergeTree)

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

### 6. Замена счётчика (VersionedCollapsingMergeTree)

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

### 7. Удаление ошибочной строки с лишним нулём (DELETE)

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

## Проверка объёмов

```sh
docker compose exec clickhouse clickhouse-client --query \
  "SELECT count() FROM energosbyt.dim_realty"
docker compose exec clickhouse clickhouse-client --query \
  "SELECT count() FROM energosbyt.dim_tariffs FINAL"
docker compose exec clickhouse clickhouse-client --query \
  "SELECT count() FROM energosbyt.fact_meter_readings FINAL"
docker compose exec clickhouse clickhouse-client --query \
  "SELECT count() FROM energosbyt.fact_invoice"
```

Для `fact_meter_readings` обязателен `FINAL`: до слияния физических строк
больше из-за корректировок.

## CI

Шаблонный workflow `.github/workflows/energosbyt.lab.yml` оставлен без изменений.
Он читает `LAB=1` из `.labrc` и вызывает переиспользуемую проверку курса
`sitnikovik/abds/.github/workflows/energosbyt.lab.yml@master`.
Проверка выполняет `make run`, затем `make setup` с таймаутом 5 минут,
запускает автограйдер и останавливает контейнеры через `docker compose down -v`.
Ручная настройка не требуется: генератор использует только `python3`, а все
зависимости ClickHouse и приложения поставляются Docker-образами.
