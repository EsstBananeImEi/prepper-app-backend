# Gunicorn Konfiguration für Prepper App

# Server socket
# bind = "0.0.0.0:4000"
backlog = 2048

# Worker processes
workers = 4  # Anzahl Worker-Prozesse (CPU-Kerne * 2 + 1)
worker_class = "sync"
worker_connections = 1000
timeout = 30  # Request timeout in Sekunden
keepalive = 2
max_requests = 1000  # Restart worker nach X requests
max_requests_jitter = 50

# Logging
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "prepper-app"

# Server mechanics
preload_app = True  # Lädt App vor dem Worker-Start
daemon = False

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Performance
worker_tmp_dir = "/dev/shm"  # Nutzt RAM für Worker-Kommunikation (falls verfügbar)

# Error handling
graceful_timeout = 30
