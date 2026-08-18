#!/bin/bash
#SBATCH --job-name=fbot-binned
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --time=08:00:00
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
ENVNAME=$(python3 -c "import yaml;print(yaml.safe_load(open('$CONFIG'))['conda_env'])")

source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh
conda activate "$ENVNAME"

LINE=$(sed -n "${SLURM_ARRAY_TASK_ID}p" tasks.txt)
EVENT=$(echo "$LINE" | awk '{print $1}')
WINDOW=$(echo "$LINE" | awk '{print $2}')
echo "task ${SLURM_ARRAY_TASK_ID}: $EVENT $WINDOW"
python run_task.py --config "$CONFIG" --event "$EVENT" --window "$WINDOW"
