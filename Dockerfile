FROM python:3.11-slim
WORKDIR /app

# Aktualisiere die Paketlisten und installiere die benötigten Build-Tools
RUN apt-get update && \
    apt-get install -y build-essential gcc g++ python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Kopiere die requirements.txt und installiere die Python-Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den restlichen Code
COPY . .

EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]