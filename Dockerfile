# ──────────────────────────────────────────────────────────────
#  Course Verifier – Docker image for headless server deployment
# ──────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm

LABEL maintainer="yugshah197@gmail.com"

# Prevent interactive apt prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV VERIFIER_NO_FORCE_EXIT=true

WORKDIR /app

# Install system deps: Chrome, fonts, Tesseract OCR, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg2 \
    ca-certificates \
    fonts-liberation \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxss1 \
    libappindicator3-1 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libxkbcommon0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome Stable (undetected_chromedriver expects it)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Playwright browsers (if needed by any helper scripts)
RUN playwright install chromium || true

# Expose dashboard port
EXPOSE 8080

# Default: run the verifier for pages 602-1890 and then serve dashboard
CMD ["python", "run_verifier_pages.py", "link_compile.pdf", "--pages", "602", "1890"]
