# Лабораторный проект

[![labs](https://github.com/AndrewTheMaster/abds-labs/actions/workflows/energosbyt.lab.yml/badge.svg)](https://github.com/AndrewTheMaster/abds-labs/actions/workflows/energosbyt.lab.yml)

Backend-сервис вымышленной ЖКХ-компании для практики по курсу «Архитектура систем обработки больших данных».

## С чего начать

1. **‼️ Настройте репозиторий** — проведите обязательную настройку контрибьюторов и защиты ветки (см. ниже)
2. **[Лабораторные работы](https://github.com/sitnikovik/abds/tree/master/lab)** — технические задания для каждой лабораторной работы
3. **[CONTRIBUTING.md](CONTRIBUTING.md)** — требования к структуре проекта, процесс разработки и проверки
4. **[Документация курса](https://github.com/sitnikovik/abds)** — методические материалы и дополнительные ресурсы

## Настройка репозитория

### Защита основной ветки

После создания репозитория из шаблона **обязательно настройте правила защиты для ветки `main`**:

1. Откройте **Settings** → **Branches** → **Add classic branch protection rule**
2. В поле **Branch name pattern** укажите: `main`
3. Включите следующие опции:
   - **Require a pull request before merging**
     - Require approvals: **1**: требует минимум одного одобрения перед слиянием
   - ***Require status checks to pass before merging***
     - Выберите *"autograder"*: проверит все лабораторные работы автоматически
     - ***Require branches to be up to date before merging*** (рекомендуется):
     требует, чтобы ветка PR была синхронизирована с последними изменениями из основной ветки перед слиянием
   - ***Do not allow bypassing the above settings***: запрещает обход настроек защиты ветки
4. Нажмите **Create** или **Save changes**

> ⚠️ **Важно:** Без этих настроек автоматические проверки не будут блокировать PR с ошибками.

### Добавление коллабораторов

Чтобы преподаватели могли проводить код-ревью:

1. Откройте **Settings** → **Collaborators**
2. Нажмите **Add people**
3. Добавьте всех кто есть в списке ревьюеров в файле [CODEOWNERS](CODEOWNERS)
4. Выберите роль: **Write** (или выше), иначе ревьюер не сможет одобрить PR

## Помощь

Возникли вопросы? → [@sitnikovik](https://t.me/sitnikovik)

---

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
├── app/main.py                 # HTTP-маршруты и JSON-ответы
├── app/service.py              # валидация и сценарии SCD
├── app/repository.py           # запросы к таблицам
├── app/clickhouse_client.py    # HTTP-клиент ClickHouse
├── scripts/generate.py         # генератор CSV-датасетов
├── scripts/ch.sh               # clickhouse-client внутри контейнера
├── scripts/load.sh             # идемпотентная загрузка CSV
├── sql/schema.sql              # схема energosbyt
├── sql/truncate.sql            # очистка таблиц перед загрузкой
├── sql/teardown.sql            # удаление базы
├── api/lab1.http               # коллекция запросов для ручной проверки API
├── docs/scenarios.md           # HTTP- и SQL-проверки SCD
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

HTTP-запросы и SQL-проверки всех семи сценариев SCD и удаления описаны в [docs/scenarios.md](docs/scenarios.md).

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
