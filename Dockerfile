FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

# System deps needed to run the app and build some wheels (keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ghostscript \
    texlive-xetex \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-science \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (for better Docker layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code from local source
COPY *.py /app/
COPY pages /app/pages
COPY tools /app/tools

# Create data directory for uploads (will be mounted as volume in production)
# Also symlink /app/data -> /data so any legacy paths write to the volume
RUN mkdir -p /data && ln -sfn /data /app/data

EXPOSE 8501
# Use sh for POSIX-compatible parameter expansion (no need for bash in slim)
CMD ["sh", "-lc", "streamlit run main_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]
