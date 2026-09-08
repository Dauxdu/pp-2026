-include .env

BACKEND ?= seq
ifeq ($(BACKEND),seq)
  LAB ?= lab_01
else ifeq ($(BACKEND),openmp)
  LAB ?= lab_02
else ifeq ($(BACKEND),mpi)
  LAB ?= lab_03
else ifeq ($(BACKEND),cuda)
  LAB ?= lab_04
endif

DATA_DIR := $(CURDIR)/data
SCRIPTS_DIR := $(CURDIR)/scripts
BUILD_DIR := $(CURDIR)/build
BUILD_BIN := $(BUILD_DIR)/src/backends/$(BACKEND)/$(BACKEND)
RESULTS_DIR := $(CURDIR)/results/$(BACKEND)
RESULTS_FILE := $(RESULTS_DIR)/results.jsonl
FIGURES_DIR := $(CURDIR)/reports/$(LAB)/figures

SIZES ?= 1 2 4 8 16 32 64 128 256 512 1024 2048 4096
CORES ?= 1 2 4
THREADS ?= 1 2 4 8
THREADED_BACKENDS ?= openmp mpi
# Аргументы потоков и ядер передаются только для многопоточных бекендов
THREADED_ARGS = $(if $(filter $(BACKEND),$(THREADED_BACKENDS)),--threads $(THREADS) --cores $(CORES),)

.PHONY: help all configure build generate_data start generate_plots

.DEFAULT_GOAL := help

help:
	@echo "Доступные команды:"
	@sed -n 's/^## //p' $(MAKEFILE_LIST) | column -t -s ':'
	@echo ""
	@echo "Пример: make start SIZES=\"128 256 512\" BACKEND=openmp THREADS=\"1 2 4\" CORES=\"1 2 4 8\""

## all: Полный цикл
all: configure build generate_data start generate_plots

## configure: Настройка CMake (требует VCPKG_ROOT)
configure:
	cmake -S "$(CURDIR)" -B "$(BUILD_DIR)" \
		-DCMAKE_TOOLCHAIN_FILE="$(VCPKG_ROOT)/scripts/buildsystems/vcpkg.cmake"

## build: Сборка бекенда
build:
	@test -f "$(BUILD_DIR)/CMakeCache.txt" || $(MAKE) configure
	cmake --build "$(BUILD_DIR)" -j

## generate_data: Генерация датасетов
generate_data:
	@mkdir -p "$(DATA_DIR)"
	@for s in $(SIZES); do \
		python3 "$(SCRIPTS_DIR)/generate_data.py" \
			--out "$(DATA_DIR)/size_$$s" \
			--range-end $$(($$s * 100000)) \
			--targets 16 \
			--size-code $$s; \
	done

## generate_plots: Построение графиков
generate_plots:
	@mkdir -p "$(FIGURES_DIR)"
	@python3 "$(SCRIPTS_DIR)/generate_plots.py" \
		--results-file "$(RESULTS_FILE)" \
		--figures-dir "$(FIGURES_DIR)"

## start: Запуск бенчмарка и верификация
start:
	python3 "$(SCRIPTS_DIR)/run_benchmark.py" \
		--binary "$(BUILD_BIN)" --data-dir "$(DATA_DIR)" --results-file "$(RESULTS_FILE)" \
		--sizes $(SIZES) $(THREADED_ARGS)
