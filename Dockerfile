# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including LaTeX
RUN apt-get update && apt-get install -y \
    texlive-xetex \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-science \
    cm-super \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Bake full dataset into the image for cloud deployment (Railway)
COPY data-full/ /app/data/

# Ensure data directory exists
RUN mkdir -p /app/data

# Expose Streamlit port
EXPOSE 8501

# Set environment variables
ENV BASE_DIR=/app/data
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# Add startup script that reads $PORT and launches Streamlit
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Run the application via startup script (ensures $PORT is honored)
CMD ["/start.sh"]
