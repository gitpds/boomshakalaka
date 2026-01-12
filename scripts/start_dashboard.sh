#!/bin/bash
# Start the Boomshakalaka Dashboard

cd /home/pds/boomshakalaka
source /home/pds/miniconda3/etc/profile.d/conda.sh
conda activate money_env

python -m dashboard.server
