bind = "0.0.0.0:5000"

# Fixed at 2 workers for t2/t3.micro (908MB RAM).
# Dynamic cpu_count()*2+1 = 5 workers caused OOM kills.
# Each Flask worker uses ~150-250MB → 2 workers = ~400MB max, leaving ~500MB headroom.
workers = 2

worker_class = "sync"
timeout = 60
keepalive = 2

# Recycle workers after 300 requests to prevent gradual memory leaks.
max_requests = 300
max_requests_jitter = 30

loglevel = "info"
accesslog = "-"
errorlog = "-"
