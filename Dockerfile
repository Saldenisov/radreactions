FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py /app/

RUN mkdir -p /data

EXPOSE 8501
CMD ["sh", "-c", "exec streamlit run public_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]
