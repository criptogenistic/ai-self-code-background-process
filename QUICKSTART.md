# Quick Start Guide

## Option 1: Direct Python (Recommended for Development)

### Prerequisites
- Python 3.8+
- pip

### Setup & Run

```bash
# 1. Clone and navigate to the repo
cd ai-self-code-background-process

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup Playwright browser
python -m playwright install chromium

# 5. Configure environment
cp .env.example .env
# Edit .env and add your API_KEYS

# 6. Run the application
python main.py
```

The API will be available at `http://localhost:8000`

---

## Option 2: Using Startup Script (Linux/macOS)

```bash
# Make script executable
chmod +x startup.sh

# Run the startup script
./startup.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Install Playwright browsers
- Create `.env` from `.env.example`
- Start the application

---

## Option 3: Docker (Recommended for Production)

### Prerequisites
- Docker
- Docker Compose

### Setup & Run

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with your settings

# 2. Build and start
docker-compose up --build

# 3. Access the API
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

---

## API Usage

### 1. Search (Immediate - Synchronous)

```bash
curl -X POST http://localhost:8000/search \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "python async programming",
    "background": false
  }'
```

Response:
```json
{
  "status": "done",
  "query": "python async programming",
  "results": [
    {
      "title": "Result Title",
      "snippet": "Result snippet...",
      "url": "https://example.com"
    }
  ]
}
```

### 2. Search (Background - Asynchronous)

```bash
curl -X POST http://localhost:8000/search \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "python async programming",
    "background": true,
    "webhook_url": "https://your-webhook.com/callback"
  }'
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

### 3. Get Results

```bash
curl http://localhost:8000/results/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer your-secret-key"
```

Response:
```json
{
  "status": "done",
  "query": "python async programming",
  "results": [...],
  "created_at": "2024-01-15T10:30:00",
  "finished_at": "2024-01-15T10:32:15"
}
```

---

## Configuration

Edit `.env` to customize:

```env
# API Keys (required if auth is enabled)
API_KEYS=key1,key2,key3

# Webhook signing (optional but recommended)
WEBHOOK_SECRET=your-secret-signing-key

# Search settings
RESULT_TTL_SECONDS=3600          # How long to keep results
MAX_RESULTS=10                    # Max results per search

# Proxy (optional)
PLAYWRIGHT_DEFAULT_PROXY=http://user:pass@proxy:3128

# Server
HOST=0.0.0.0
PORT=8000
```

---

## Interactive API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Troubleshooting

### Playwright browser not found
```bash
python -m playwright install chromium
```

### Port already in use
Change `PORT` in `.env` to an available port

### API key authentication failing
- Ensure `API_KEYS` is set in `.env`
- Use: `Authorization: Bearer your-key` header

### Webhook delivery failed
- Check `webhook_url` is HTTPS and accessible
- Set `WEBHOOK_SECRET` in `.env` for signing

---

## Stopping the Application

**Direct Python**: `Ctrl+C`

**Docker**: `docker-compose down`
