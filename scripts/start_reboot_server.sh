#!/bin/bash
# Start the Reboot Server

cd /home/pds/boomshakalaka
source /home/pds/miniconda3/etc/profile.d/conda.sh
conda activate money_env

python scripts/reboot_server.py
