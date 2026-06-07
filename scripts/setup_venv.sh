#!/usr/bin/env bash
# Isolated env avoids mixing pip matplotlib with Ubuntu's python3-matplotlib (Axes3D warning).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "from mpl_toolkits.mplot3d import Axes3D; import matplotlib; print('matplotlib', matplotlib.__version__, '— Axes3D OK')"
