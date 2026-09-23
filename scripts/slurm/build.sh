#!/bin/bash
set -euo pipefail

MPICXX="${MPICXX:-mpicxx}"

if ! command -v "$MPICXX" >/dev/null 2>&1; then
    if command -v mpiicpc >/dev/null 2>&1; then
        MPICXX=mpiicpc
    else
        echo "ОШИБКА: не найден mpicxx/mpiicpc. Сначала: module load intel/mpi4" >&2
        echo "Проверьте доступные модули: module avail 2>&1 | grep -i mpi" >&2
        exit 1
    fi
fi

echo "Компилятор: $MPICXX"
"$MPICXX" --version 2>&1 | head -1 || true

"$MPICXX" -std=c++11 -O3 -Wall \
-I src/core \
src/backends/mpi/main.cpp \
-o mpi

echo "Готово: ./mpi"
