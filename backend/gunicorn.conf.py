"""
BeakMask Gunicorn Configuration
生產環境 WSGI 伺服器配置
"""
import multiprocessing
import os

# Bind
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:5000')

# Workers
# Rule of thumb: 2-4 x $(NUM_CORES)
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
worker_connections = 1000
max_requests = 1000  # Restart workers after this many requests (prevent memory leaks)
max_requests_jitter = 50

# Threads
threads = int(os.getenv('GUNICORN_THREADS', 2))

# Timeout
timeout = 30  # Request timeout
graceful_timeout = 30  # Graceful shutdown timeout
keepalive = 2

# Security
limit_request_line = 4094  # Max URL length
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = '-'  # stdout
errorlog = '-'   # stderr
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'beakmask'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Preload app for faster worker spawning
preload_app = True


def on_starting(server):
    """Called just before the master process is initialized."""
    pass


def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    pass


def worker_int(worker):
    """Called when a worker received SIGINT or SIGQUIT."""
    pass


def worker_abort(worker):
    """Called when a worker received SIGABRT."""
    pass
