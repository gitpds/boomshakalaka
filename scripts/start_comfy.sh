#!/bin/bash
# Start ComfyUI in headless mode for AI Studio

cd /home/pds/image_gen/ComfyUI
source /home/pds/miniconda3/etc/profile.d/conda.sh
conda activate money_env

# Start ComfyUI listening on localhost only (privacy)
python main.py --listen 127.0.0.1
