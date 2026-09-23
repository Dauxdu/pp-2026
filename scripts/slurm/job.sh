#!/bin/bash
#SBATCH --job-name=pp-2026
#SBATCH --partition=batch
#SBATCH --ntasks-per-node=8
#SBATCH --time=24:00:00
#SBATCH --output=mpi-series-%j.out

set -u

SIZES="1 2 4 8 16 32 64 128 256 512 1024 2048 4096"
NPROCS="1 2 4 8"

ROOT="$SLURM_SUBMIT_DIR"
OUT="${ROOT}/results/mpi"
mkdir -p "$OUT"

module load intel/mpi5

echo "size_code,processes,time_seconds" > "${OUT}/summary.csv"

for s in $SIZES; do
    cfg="${ROOT}/data/size_${s}/config.json"
    if [ ! -f "$cfg" ]; then
        echo "ПРОПУСК size=$s: нет $cfg"
        continue
    fi
    for np in $NPROCS; do
        out="${OUT}/size_${s}_np${np}.json"
        echo ">>> size=$s np=$np"
        mpirun -r ssh -np "$np" "${ROOT}/mpi" --config "$cfg" --output "$out"
        if [ -f "$out" ]; then
            t=$(grep -o '"time_seconds"[^,}]*' "$out" | head -1 | sed 's/.*: *//')
            echo "${s},${np},${t}" >> "${OUT}/summary.csv"
        fi
    done
done

echo "Готово. Результаты в ${OUT}/"
