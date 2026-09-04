# Переменные путей
PWD := $(shell pwd)
DATA_DIR := $(PWD)/data
RESULTS_DIR := $(PWD)/results
FIGURES_DIR := $(PWD)/figures
SCRIPTS_DIR := $(PWD)/scripts
BUILD_BIN := $(PWD)/build/clang-vcpkg-debug/lab/lab_01/lab_01

# Списки размеров для разных сценариев
SIZES_ALL := 1 2 4 8 16 32 64 128 256 512 1024 2048 4096
SIZES_SMALL := 1 2 4 8 16 32
SIZES_MEDIUM := 32 64 128 256
SIZES_LARGE := 512 1024 2048 4096

.PHONY: help all generate_data generate_plots start_all start_small start_medium start_large

# Цель по умолчанию теперь вызывает справку
.DEFAULT_GOAL := help

## help: Показать это справочное сообщение.
help:
	@echo "Доступные команды:"
	@sed -n 's/^## //p' $(MAKEFILE_LIST) | column -t -s ':'

## all: Запустить полный цикл (генерация данных -> тесты -> графики).
all: generate_data start_all generate_plots

## generate_data: Сгенерировать входные данные для всех размеров (1-4096).
generate_data:
	@for s in $(SIZES_ALL); do \
		python "$(SCRIPTS_DIR)/generate_data.py" \
			--out "$(DATA_DIR)/size_$$s" \
			--range-end $$(($$s * 100000)) \
			--targets 16 \
			--size-code $$s; \
	done

## generate_plots: Построить графики на основе полученных результатов.
generate_plots:
	@python "$(SCRIPTS_DIR)/generate_plots.py" \
		--results-dir "$(RESULTS_DIR)" \
		--figures-dir "$(FIGURES_DIR)"

# Внутренний макрос для запуска тестов и верификации
define run_and_verify
	@mkdir -p "$(RESULTS_DIR)"
	@for s in $(1); do \
		"$(BUILD_BIN)" \
			--config "$(DATA_DIR)/size_$$s/config.json" \
			--output "$(RESULTS_DIR)/size_$$s.json"; \
		python "$(SCRIPTS_DIR)/verify_results.py" \
			--config "$(DATA_DIR)/size_$$s/config.json" \
			--expected "$(DATA_DIR)/size_$$s/expected.jsonl" \
			--result "$(RESULTS_DIR)/size_$$s.json"; \
	done
endef

## start_all: Запустить расчеты и верификацию для ВСЕХ размеров.
start_all:
	$(call run_and_verify,$(SIZES_ALL))

## start_small: Запустить расчеты и верификацию только для МАЛЕНЬКИХ размеров (1-32).
start_small:
	$(call run_and_verify,$(SIZES_SMALL))

## start_medium: Запустить расчеты и верификацию только для СРЕДНИХ размеров (32-256).
start_medium:
	$(call run_and_verify,$(SIZES_MEDIUM))

## start_large: Запустить расчеты и верификацию только для БОЛЬШИХ размеров (512-4096).
start_large:
	$(call run_and_verify,$(SIZES_LARGE))
