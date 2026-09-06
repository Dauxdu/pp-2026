# Лабораторные работы по параллельному программированию

Подробности и результаты конкретной лабы — в её собственном отчёте:

- [**Лабораторная работа 1**](reports/lab_01/README.md) — последовательная версия.

## О чём репозиторий

Задание — распараллелить вычислительную задачу и на каждом шаге сравнивать производительность: последовательно → OpenMP → MPI → CUDA.

**Аудит синтетических парольных хешей.** Программа перебирает диапазон целочисленных индексов, каждый индекс превращает в пароль фиксированной длины по заданному алфавиту, считает `SHA256(salt + password)` и проверяет хеш по списку из 16 заранее известных «целевых» хешей.

## Архитектура

- **`src/audit.hpp`, `src/sha256.hpp`** — вся предметная логика, общая для всех бэкендов: разбор `config.json`, индекс целей (`TargetIndex`), счётчик кандидатов (`CandidateCounter`), собственная реализация SHA-256, секундомер, запись `result.json`.
- **`src/<backend>/main.cpp`** — тонкий слой, отвечающий только за способ перебора диапазона: `seq` — один поток целиком, `openmp`/`mpi`/`cuda` диапазон, поделённый на потоки/процессы/GPU-блоки.

Все бэкенды на одних и тех же входных данных обязаны находить одни и те же 16 паролей — меняется только время работы.

## Методика эксперимента

### Данные

Для кода размера `N` генератор `scripts/generate_data.py` создаёт `data/size_N/` с диапазоном `range_end = N · 100 000`:

- `config.json` — параметры задачи (алфавит, длина пароля, соль, диапазон);
- `targets.jsonl` — только `id` + `hash` 16 целей;
- `expected.jsonl` — эталон (`id`, `index`, `password`, `hash`), посчитанный отдельно с помощью Python.

Полное пространство паролей (`36^8 ≈ 2,8·10¹²`) на порядки больше любого использованного диапазона — коллизии индексов исключены.

### Замер

Секундомер (`std::chrono::steady_clock`) включается сразу перед основным циклом перебора и выключается сразу после — чтение конфигурации и запись результата в замер не входят. Каждый прогон пишет `results/<backend>/size_N.json` с полями `candidates_checked`, `time_seconds`, `throughput_per_second`, `matches`.

### Верификация

`scripts/verify_results.py` после каждого прогона сверяет `candidates_checked` с ожидаемым объёмом и построчно — весь набор найденных
`{id, password, hash}` с `expected.jsonl`.
Выводит `VERIFICATION OK` или `VERIFICATION FAILED` соответственно.

### Агрегация

`scripts/generate_plots.py` собирает `size_*.json` в `results.csv` и строит графики в `reports/lab_XX/figures/`.

## Требования

- CMake ≥ 4.2, Ninja, компилятор GCC или Clang;
- vcpkg с переменной окружения `VCPKG_ROOT`;
- Python 3.10+, `make`;
- Python-пакет `matplotlib`.

## Подготовка и быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\Activate.ps1     # Windows (PowerShell)

pip install --upgrade pip
pip install -r requirements.txt
```

Общий цикл для любого бэкенда — один и тот же набор целей `Makefile`, меняется только `BACKEND`/`LAB`:

```bash
make generate_data                             # датасеты data/size_* (SIZES_ALL)
make build                                     # сборка (первый запуск сам сделает configure)
make start_small    BACKEND=seq LAB=lab_01     # быстрый прогон + верификация
make start_all      BACKEND=seq LAB=lab_01     # полный прогон по всем размерам
make generate_plots BACKEND=seq LAB=lab_01     # results.csv + графики
```

## Структура репозитория

```
pp-2026/
├── CMakeLists.txt
├── CMakePresets.json
├── Makefile
├── vcpkg.json
├── requirements.txt
├── src/
│   ├── CMakeLists.txt
│   ├── audit.hpp
│   ├── sha256.hpp
│   ├── seq/{CMakeLists.txt, main.cpp}
│   ├── openmp/{CMakeLists.txt, main.cpp}
│   ├── mpi/{CMakeLists.txt, main.cpp}
│   └── cuda/{CMakeLists.txt, main.cu}
├── scripts/
│   ├── generate_data.py
│   ├── verify_results.py
│   └── generate_plots.py
├── data/size_*/
├── results/<backend>/
└── reports/lab_0X/{README.md, figures/}
```
