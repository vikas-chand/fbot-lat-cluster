#!/bin/bash
#PBS -N fbot-binned
#PBS -j oe
#PBS -o logs/
#PBS -l walltime=24:00:00      # measured ~23 h/task; resume covers any overrun
#PBS -l nodes=1:ppn=4
# Array submission:  qsub -t 1-$(wc -l < tasks.txt)%20 submit_pbs.sh
# (Karwin's own package targets PBS, so this wrapper mirrors his usage; use it
#  on Partha's cluster if it runs PBS/Torque. Same run_task.py underneath.)

set -euo pipefail
cd "$PBS_O_WORKDIR"
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

TASKID=${PBS_ARRAYID:-$PBS_ARRAY_INDEX}
LINE=$(sed -n "${TASKID}p" tasks.txt)
EVENT=$(echo "$LINE" | awk '{print $1}')
WINDOW=$(echo "$LINE" | awk '{print $2}')
echo "task ${TASKID}: $EVENT $WINDOW"
python run_task.py --config "$CONFIG" --event "$EVENT" --window "$WINDOW"
