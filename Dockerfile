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

# Erstelle Verzeichnis für Datenbank (falls lokal gespeichert)
RUN mkdir -p /var/data && chmod 755 /var/data

# Setze Umgebungsvariablen für Produktion
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Verwende die Gunicorn-Konfiguration
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:application"]