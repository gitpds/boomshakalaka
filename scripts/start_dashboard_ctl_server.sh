#!/bin/bash
# Start the Dashboard Control Server (port 3004)

cd /home/pds/boomshakalaka
source /home/pds/miniconda3/etc/profile.d/conda.sh
conda activate money_env

python scripts/dashboard_ctl_server.py
