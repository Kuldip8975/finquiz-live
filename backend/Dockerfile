FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config.py db.py game.py questions.py ratelimit.py server.py ./

# Never run as root inside the container.
RUN useradd --create-home --uid 10001 quiz
USER quiz

EXPOSE 5000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2).status != 200)"

# One worker on purpose: live game timers and sockets share one process.
# Each open socket holds a thread, so there are far more threads than the
# connection cap in config.py (MAX_CONNECTIONS_TOTAL = 400).
CMD ["gunicorn", "-w", "1", "--threads", "512", "-b", "0.0.0.0:5000", "--timeout", "0", "--graceful-timeout", "10", "server:app"]
