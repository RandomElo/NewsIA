FROM python:3.11-slim

ENV TZ=Europe/Paris \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# cron + tzdata + xvfb + libs runtime nécessaires à Chromium (Playwright)
RUN apt-get update && apt-get install -y --no-install-recommends \
        cron \
        tzdata \
        xvfb \
        wget \
        xauth \
        ca-certificates \
        gcc \
        g++ \
        make \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY traitements/requirements.txt ./traitements/requirements.txt
RUN pip install --no-cache-dir -r traitements/requirements.txt

# Chromium + toutes ses libs système (playwright install --with-deps s'en charge)
RUN python -m playwright install --with-deps chromium

# Code de l'application
COPY traitements ./traitements

# Crontab dédiée à ce conteneur
COPY traitements/crontab /etc/cron.d/traitements-cron
RUN chmod 0644 /etc/cron.d/traitements-cron \
    && crontab /etc/cron.d/traitements-cron \
    && touch /var/log/cron.log

COPY traitements/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]