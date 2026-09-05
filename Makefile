# Переменные путей
PWD := $(shell pwd)
DATA_DIR := $(PWD)/data
RESULTS_DIR := $(PWD)/results/$(BACKEND)
FIGURES_DIR := $(PWD)/reports/$(LAB)/figures
SCRIPTS_DIR := $(PWD)/scripts
BUILD_DIR := $(PWD)/build
BUILD_BIN := $(BUILD_DIR)/src/$(BACKEND)/$(BACKEND)
BACKEND ?= seq
LAB ?= lab_01

# Списки размеров для разных сценариев
SIZES_ALL := 1 2 4 8 16 32 64 128 256 512 1024 2048 4096
SIZES_SMALL := 1 2 4 8 16 32
SIZES_MEDIUM := 32 64 128 256
SIZES_LARGE := 512 1024 2048 4096

.PHONY: help all configure build generate_data generate_plots start_all start_small start_medium start_large

.DEFAULT_GOAL := help

help:
	@echo "Доступные команды:"
	@sed -n 's/^## //p' $(MAKEFILE_LIST) | column -t -s ':'

## all: Полный цикл на малом наборе (1-32)
all: configure build generate_data start_all generate_plots

## configure: Сконфигурировать CMake-проект через vcpkg (нужен VCPKG_ROOT).
configure:
	cmake -S "$(PWD)" -B "$(BUILD_DIR)" \
		-DCMAKE_TOOLCHAIN_FILE="$(VCPKG_ROOT)/scripts/buildsystems/vcpkg.cmake"

## build: Собрать бинарник.
build:
	@test -f "$(BUILD_DIR)/CMakeCache.txt" || $(MAKE) configure
	cmake --build "$(BUILD_DIR)" -j

## generate_data: Сгенерировать входные данные.
generate_data:
	@mkdir -p "$(DATA_DIR)"
	@for s in $(SIZES_ALL); do \
		python3 "$(SCRIPTS_DIR)/generate_data.py" \
			--out "$(DATA_DIR)/size_$$s" \
			--range-end $$(($$s * 100000)) \
			--targets 16 \
			--size-code $$s; \
	done

## generate_plots: Построить графики на основе результатов текущего BACKEND.
generate_plots:
	@mkdir -p "$(FIGURES_DIR)"
	@python3 "$(SCRIPTS_DIR)/generate_plots.py" \
		--results-dir "$(RESULTS_DIR)" \
		--figures-dir "$(FIGURES_DIR)"

# Внутренний макрос: прогнать бинарник и сразу проверить результат.
define run_and_verify
	@mkdir -p "$(RESULTS_DIR)"
	@for s in $(1); do \
		"$(BUILD_BIN)" \
			--config "$(DATA_DIR)/size_$$s/config.json" \
			--output "$(RESULTS_DIR)/size_$$s.json"; \
		python3 "$(SCRIPTS_DIR)/verify_results.py" \
			--config "$(DATA_DIR)/size_$$s/config.json" \
			--expected "$(DATA_DIR)/size_$$s/expected.jsonl" \
			--result "$(RESULTS_DIR)/size_$$s.json"; \
	done
endef

## start_all: Запустить расчёты и верификацию для ВСЕХ размеров.
start_all:
	$(call run_and_verify,$(SIZES_ALL))

## start_small: Запустить расчёты и верификацию для МАЛЕНЬКИХ размеров (1-32).
start_small:
	$(call run_and_verify,$(SIZES_SMALL))

## start_medium: Запустить расчёты и верификацию для СРЕДНИХ размеров (32-256).
start_medium:
	$(call run_and_verify,$(SIZES_MEDIUM))

## start_large: Запустить расчёты и верификацию для БОЛЬШИХ размеров (512-4096).
start_large:
	$(call run_and_verify,$(SIZES_LARGE))
