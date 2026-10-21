FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY build ./build
COPY server ./server
COPY css ./css
COPY js ./js
COPY images ./images
# Railway injects PORT. Keep ONE worker: the build lock, rate limiter and
# publish lock are in-process. SITE_ROOT defaults to /tmp/bch-site.
CMD gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT --timeout 60 --access-logfile - server.wsgi:app
