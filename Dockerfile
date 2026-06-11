FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Public app only serves cached data/PDF files. No TeX/PDF compilation on Railway.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (for better Docker layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Copy the public application code.
COPY *.py /app/

# Runtime data is stored on the Railway volume mounted at /data.
RUN mkdir -p /data

EXPOSE 8501
# Use bash to properly handle signals and parameter expansion
CMD ["bash", "-c", "exec streamlit run public_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]
