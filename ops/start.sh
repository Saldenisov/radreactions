#!/usr/bin/env sh
set -e

PORT_TO_USE="${PORT:-8501}"
echo "Starting Streamlit on port ${PORT_TO_USE}..."
exec streamlit run app/main_app.py --server.port=${PORT_TO_USE} --server.address=0.0.0.0 --server.headless=true
