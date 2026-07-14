FROM mcr.microsoft.com/playwright/python:v1.49.1-noble AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_SERVICE=agent \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs npm \
    && npm install -g typescript typescript-language-server pyright \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system arceus \
    && adduser --system --ingroup arceus arceus

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

USER arceus
EXPOSE 8000

CMD ["python", "railway_start.py"]
