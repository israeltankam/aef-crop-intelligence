# image Python minimale
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# dépendances système fréquentes (ajuste si besoin)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates pkg-config \
    libpq-dev libgdal-dev libgeos-dev libxml2-dev libxslt1-dev \
 && rm -rf /var/lib/apt/lists/*

# copier requirements et installer
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r /app/requirements.txt

# copier le code
COPY . /app

EXPOSE 8501

# lancer streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.enableCORS=false"]
