"""
app.py

Playwright-based Google typing searcher with background jobs, webhook delivery, API key auth, and proxy support.
Do NOT commit secrets. Use environment variables to configure API_KEYS, WEBHOOK_SECRET, PLAYWRIGHT_DEFAULT_PROXY, etc.
"""

import asyncio
import os
import random
import uuid
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PWTimeoutError

# Config (override via env)
RESULT_TTL_SECONDS = int(os.getenv("RESULT_TTL_SECONDS", str(60 * 60)))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "10"))
PLAYWRIGHT_DEFAULT_PROXY = os.getenv("PLAYWRIGHT_DEFAULT_PROXY")  # e.g. "http://user:pass@proxy:3128"
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # optional: used to HMAC-sign webhook payloads
WEBHOOK_MAX_RETRIES = int(os.getenv("WEBHOOK_MAX_RETRIES", "5"))
WEBHOOK_TIMEOUT_SECONDS = int(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "10"))

app = FastAPI(title="Google-typing Searcher (Playwright) with Auth, Proxy, Webhook")

# In-memory stores (demo). Use persistent storage for production.
_jobs: Dict[str, Dict[str, Any]] = {}
_results_lock = asyncio.Lock()
_job_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

security = HTTPBearer(auto_error=False)


class SearchRequest(BaseModel):
    query: str
    background: Optional[bool] = False
    webhook_url: Optional[HttpUrl] = None  # if provided, results will be POSTed on completion
    proxy: Optional[str] = None  # per-request proxy override (e.g. "http://user:pass@host:port")


def _parse_proxy_url(proxy_url: str) -> Dict[str, str]:
    """
    Convert a proxy URL into playwright proxy dict:
    - playwright.launch(proxy={'server': 'http://host:port', 'username': 'u', 'password': 'p'})
    Supports http(s) and socks proxy formats.
    """
    p = urlparse(proxy_url)
    if not p.scheme or not p.hostname:
        raise ValueError("Invalid proxy URL")
    server = f"{p.scheme}://{p.hostname}"
    if p.port:
        server += f":{p.port}"
    proxy = {"server": server}
    if p.username:
        proxy["username"] = p.username
    if p.password:
        proxy["password"] = p.password
    return proxy


async def require_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """
    Simple API-key auth. Accepts:
      - Header: X-API-Key: <key>
      - Authorization: Bearer <key>
    Keys are configured in env API_KEYS (comma-separated). If API_KEYS is empty, auth is disabled.
    """
    if not API_KEYS:
        return  # auth disabled when no keys configured

    header_key = request.headers.get("x-api-key")
    token = None
    if header_key:
        token = header_key.strip()
    elif credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials.strip()

    if not token or token not in API_KEYS:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def human_type(page: Page, selector: str, text: str, min_delay_ms=50, max_delay_ms=140):
    await page.focus(selector)
    await page.fill(selector, "")
    for ch in text:
        await page.type(selector, ch, delay=random.randint(min_delay_ms, max_delay_ms))
    await asyncio.sleep(random.uniform(0.08, 0.3))


async def extract_results_from_page(page: Page, max_results: int = MAX_RESULTS) -> List[Dict[str, str]]:
    try:
        await page.wait_for_selector("div#search", timeout=7000)
    except PWTimeoutError:
        return []

    nodes = await page.query_selector_all("div#search .g")
    results = []
    for node in nodes:
        if len(results) >= max_results:
            break
        try:
            h3 = await node.query_selector("h3")
            if not h3:
                continue
            title = (await h3.inner_text()).strip()
            a = await node.query_selector("a")
            url = await a.get_attribute("href") if a else None
            snippet_el = (
                await node.query_selector("div.IsZvec")
                or await node.query_selector("div.VwiC3b")
                or await node.query_selector("span.aCOpRe")
            )
            snippet = (await snippet_el.inner_text()).strip() if snippet_el else ""
            results.append({"title": title, "snippet": snippet, "url": url})
        except Exception:
            continue
    return results


async def run_playwright_search(query: str, headless: bool = True, timeout: int = 30, proxy_url: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Launch Playwright Chromium, optionally using proxy_url (string).
    """
    proxy = None
    if proxy_url:
        proxy = _parse_proxy_url(proxy_url)
    elif PLAYWRIGHT_DEFAULT_PROXY:
        proxy = _parse_proxy_url(PLAYWRIGHT_DEFAULT_PROXY)

    async with async_playwright() as p:
        launch_kwargs = {"headless": headless}
        if proxy:
            # playwright accepts proxy parameter at launch time
            launch_kwargs["proxy"] = proxy
        browser: Browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        ))
        page = await context.new_page()
        await page.goto("https://www.google.com/ncr", timeout=timeout * 1000)

        # Try to close cookie/consent dialogs if present
        try:
            for sel in ["button:has-text('I agree')", "button:has-text('I Agree')",
                        "button:has-text('Accept all')", "button:has-text('Accept')",
                        "button:has-text('AGREE')"]:
                btn = await page.query_selector(sel)
                if btn:
                    try:
                        await btn.click()
                        await asyncio.sleep(0.5)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        search_selector = 'input[name="q"]'
        await page.wait_for_selector(search_selector, timeout=5000)
        await human_type(page, search_selector, query)
        await page.keyboard.press("Enter")
        await asyncio.sleep(random.uniform(0.6, 1.2))
        results = await extract_results_from_page(page, max_results=MAX_RESULTS)

        if not results:
            try:
                btn = await page.query_selector('input[name="btnK"]')
                if btn:
                    await btn.click()
                    await asyncio.sleep(1.0)
                    results = await extract_results_from_page(page, max_results=MAX_RESULTS)
            except Exception:
                pass

        await context.close()
        await browser.close()
        return results


def _sign_payload(payload_bytes: bytes) -> Optional[str]:
    if not WEBHOOK_SECRET:
        return None
    sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    # use header format: sha256=<hex>
    return f"sha256={sig}"


async def deliver_webhook_with_retries(webhook_url: str, payload: Dict[str, Any], max_retries: int = WEBHOOK_MAX_RETRIES):
    """
    Post JSON payload to webhook_url with HMAC signature header. Retries with exponential backoff.
    Returns (delivered: bool, last_status_code: Optional[int], attempts: int)
    """
    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = _sign_payload(payload_bytes)
    headers = {"Content-Type": "application/json"}
    if signature:
        headers["X-Signature"] = signature

    attempt = 0
    last_status = None
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS, follow_redirects=False) as client:
        while attempt < max_retries:
            attempt += 1
            try:
                resp = await client.post(webhook_url, content=payload_bytes, headers=headers)
                last_status = resp.status_code
                if 200 <= resp.status_code < 300:
                    return True, resp.status_code, attempt
            except Exception:
                last_status = None
            # backoff
            await asyncio.sleep(min(30, (2 ** attempt) + random.uniform(0, 1)))
    return False, last_status, attempt


async def background_worker():
    while True:
        job = await _job_queue.get()
        job_id = job["job_id"]
        query = job["query"]
        webhook_url = job.get("webhook_url")
        proxy = job.get("proxy")
        started = datetime.utcnow()
        async with _results_lock:
            _jobs[job_id] = {
                "status": "running",
                "query": query,
                "created_at": started.isoformat(),
                "results": None,
                "error": None,
                "webhook_url": webhook_url,
                "webhook_attempts": 0,
                "webhook_last_status": None,
            }
        try:
            results = await run_playwright_search(query, headless=True, proxy_url=proxy)
            finished_at = datetime.utcnow().isoformat()
            async with _results_lock:
                _jobs[job_id].update({
                    "status": "done",
                    "results": results,
                    "finished_at": finished_at,
                })
        except Exception as e:
            finished_at = datetime.utcnow().isoformat()
            async with _results_lock:
                _jobs[job_id].update({
                    "status": "error",
                    "error": repr(e),
                    "finished_at": finished_at,
                })

        # If a webhook was provided, deliver results (with retries) and track attempts/status
        if webhook_url:
            async with _results_lock:
                snapshot = _jobs[job_id].copy()
            payload = {
                "job_id": job_id,
                "status": snapshot.get("status"),
                "query": snapshot.get("query"),
                "results": snapshot.get("results"),
                "error": snapshot.get("error"),
                "created_at": snapshot.get("created_at"),
                "finished_at": snapshot.get("finished_at"),
            }
            delivered, last_status, attempts = await deliver_webhook_with_retries(webhook_url, payload)
            async with _results_lock:
                _jobs[job_id]["webhook_attempts"] = attempts
                _jobs[job_id]["webhook_last_status"] = last_status
                _jobs[job_id]["webhook_delivered"] = delivered

        _job_queue.task_done()


@app.on_event("startup")
async def startup_event():
    # start background worker(s)
    asyncio.create_task(background_worker())
    asyncio.create_task(result_cleanup_task())


async def result_cleanup_task():
    while True:
        await asyncio.sleep(60)
        cutoff = datetime.utcnow() - timedelta(seconds=RESULT_TTL_SECONDS)
        async with _results_lock:
            to_delete = [jid for jid, v in _jobs.items()
                         if "finished_at" in v and datetime.fromisoformat(v["finished_at"]) < cutoff]
            for jid in to_delete:
                del _jobs[jid]


@app.post("/search", dependencies=[Depends(require_api_key)])
async def search(req: SearchRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    # Validate webhook URL if provided
    if req.webhook_url:
        # Basic sanity: http(s) only
        if not (req.webhook_url.scheme in ("http", "https")):
            raise HTTPException(status_code=400, detail="webhook_url must be http or https")

    if req.background:
        job_id = str(uuid.uuid4())
        async with _results_lock:
            _jobs[job_id] = {
                "status": "queued",
                "query": query,
                "created_at": datetime.utcnow().isoformat(),
                "webhook_url": str(req.webhook_url) if req.webhook_url else None,
                "proxy": req.proxy or None,
            }
        await _job_queue.put({"job_id": job_id, "query": query, "webhook_url": str(req.webhook_url) if req.webhook_url else None, "proxy": req.proxy})
        return {"job_id": job_id, "status": "queued"}
    else:
        # immediate: run and optionally deliver webhook synchronously
        try:
            results = await run_playwright_search(query, headless=True, proxy_url=req.proxy)
            response = {"status": "done", "query": query, "results": results}
            if req.webhook_url:
                payload = {
                    "job_id": "inline-" + str(uuid.uuid4()),
                    "status": "done",
                    "query": query,
                    "results": results,
                    "error": None,
                    "created_at": datetime.utcnow().isoformat(),
                    "finished_at": datetime.utcnow().isoformat(),
                }
                delivered, last_status, attempts = await deliver_webhook_with_retries(str(req.webhook_url), payload)
                response["webhook_delivered"] = delivered
                response["webhook_last_status"] = last_status
                response["webhook_attempts"] = attempts
            return response
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@app.get("/results/{job_id}", dependencies=[Depends(require_api_key)])
async def get_results(job_id: str):
    async with _results_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
