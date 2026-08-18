#!/bin/bash
#PBS -N fbot-binned
#PBS -j oe
#PBS -o logs/
#PBS -l walltime=08:00:00
#PBS -l nodes=1:ppn=4
# Array submission:  qsub -t 1-$(wc -l < tasks.txt)%20 submit_pbs.sh
# (Karwin's own package targets PBS, so this wrapper mirrors his usage; use it
#  on Partha's cluster if it runs PBS/Torque. Same run_task.py underneath.)

set -euo pipefail
cd "$PBS_O_WORKDIR"
mkdir -p logs
CONFIG=${CONFIG:-cluster_config.yaml}
ENVNAME=$(python3 -c "import yaml;print(yaml.safe_load(open('$CONFIG'))['conda_env'])")

source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh
conda activate "$ENVNAME"

TASKID=${PBS_ARRAYID:-$PBS_ARRAY_INDEX}
LINE=$(sed -n "${TASKID}p" tasks.txt)
EVENT=$(echo "$LINE" | awk '{print $1}')
WINDOW=$(echo "$LINE" | awk '{print $2}')
echo "task ${TASKID}: $EVENT $WINDOW"
python run_task.py --config "$CONFIG" --event "$EVENT" --window "$WINDOW"
