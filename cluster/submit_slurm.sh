#!/bin/bash
#SBATCH --job-name=fbot-binned
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --time=24:00:00        # measured ~23 h/task; resume covers any overrun
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
# Array size is set at submit time:  sbatch --array=1-$(wc -l < tasks.txt)%20 submit_slurm.sh
# The %20 throttle limits concurrent tasks; tune to the allocation.
# LSU HPC (SuperMike-3 etc.) and most modern clusters use SLURM.

set -euo pipefail
mkdir -p logs
CONFIG=${CONFIG:-cluster_config.yaml}
# Read the env name WITHOUT needing python+PyYAML before the env exists: on many
# clusters the stock python3 has no yaml and `set -e` would kill the job here.
ENVNAME=$(sed -n 's/^conda_env:[[:space:]]*//p' "$CONFIG" | sed 's/#.*//; s/["'"'"'"'"'"']//g; s/[[:space:]]*$//')

source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh
conda activate "$ENVNAME"

# Resume is on by default: a killed task keeps its finished index rows
# and its preprocessing. Set FS_RESUME=0 to force a clean recompute.
export FS_RESUME=${FS_RESUME:-1}

LINE=$(sed -n "${SLURM_ARRAY_TASK_ID}p" tasks.txt)
EVENT=$(echo "$LINE" | awk '{print $1}')
WINDOW=$(echo "$LINE" | awk '{print $2}')
echo "task ${SLURM_ARRAY_TASK_ID}: $EVENT $WINDOW"
python run_task.py --config "$CONFIG" --event "$EVENT" --window "$WINDOW"
