"""GitHub aktivnost (commitovi) za zadani repozitorij - fundamentalni signal za altcoine: "ako
marketing raste, a GitHub miruje, potencijalni problem" (iz korisnikovog popisa). Besplatan GitHub
REST API: bez ključa 60 zahtjeva/sat po IP-u, s besplatnim Personal Access Tokenom (classic, bez
posebnih dopuštenja - samo za čitanje javnih repozitorija) 5000/sat.

UŽIVO TESTIRANO (23.11.2026., okruženje s izlaznim internet pristupom): HTTP 403, ali NE GitHubov
stvarni rate limit - poruka je specifična za OVO razvojno sandbox okruženje ("GitHub access to
this repository is not enabled for this session"), koje izravne REST pozive prema api.github.com
preusmjerava/blokira i traži korištenje vlastitog GitHub MCP alata umjesto raw API poziva. Na
korisnikovom običnom računalu (ili bilo gdje izvan ovog specifičnog sandboxa) ovaj klijent bi
trebao raditi normalno prema stvarnim GitHub rate limitima (60/sat bez tokena, 5000/sat s njim).
"""
import calendar
import time

import httpx

from app.config import GITHUB_TOKEN

GITHUB_API = "https://api.github.com"

# Oznaka -> "owner/repo".
REPOS = {
    "BTC_CORE": "bitcoin/bitcoin",
    "ETH_GO": "ethereum/go-ethereum",
    "SOL_CORE": "solana-labs/solana",
}


class GitHubError(Exception):
    pass


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _fetch_commits_page(repo: str, since_iso: str, page: int = 1) -> list[dict]:
    with httpx.Client(timeout=20) as client:
        resp = client.get(
            f"{GITHUB_API}/repos/{repo}/commits",
            params={"since": since_iso, "per_page": 100, "page": page},
            headers=_headers(),
        )
    if resp.status_code == 403:
        raise GitHubError(f"HTTP 403 (vjerojatno rate limit - dodaj GITHUB_TOKEN u .env): {resp.text[:300]}")
    if resp.status_code != 200:
        raise GitHubError(f"HTTP {resp.status_code} od GitHuba za {repo}: {resp.text[:300]}")
    data = resp.json()
    if not isinstance(data, list):
        raise GitHubError(f"Neočekivan GitHub odgovor za {repo}: {str(data)[:300]}")
    return data


def _daily_commit_counts(repo: str, since_ts: int) -> list[tuple[int, float]]:
    import datetime

    since_iso = datetime.datetime.fromtimestamp(since_ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_day: dict[int, int] = {}
    page = 1
    while True:
        commits = _fetch_commits_page(repo, since_iso, page)
        if not commits:
            break
        for commit in commits:
            date_str = commit.get("commit", {}).get("author", {}).get("date")
            if not date_str:
                continue
            ts = calendar.timegm(time.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ"))
            day_ts = ts - (ts % 86400)
            by_day[day_ts] = by_day.get(day_ts, 0) + 1
        if len(commits) < 100 or page >= 10:  # sigurnosni limit stranica po pozivu
            break
        page += 1
    points = [(day, float(count)) for day, count in by_day.items()]
    points.sort()
    return points


def fetch_recent(label: str, days: int = 90) -> list[tuple[int, float]]:
    repo = REPOS.get(label, label)
    since_ts = int(time.time() - days * 86400)
    return _daily_commit_counts(repo, since_ts)


def sync_to_db(conn, label: str) -> int:
    import datetime

    from app.macro_store import save_series

    repo = REPOS.get(label, label)
    since_ts = int(time.time() - 365 * 86400)  # GitHub "since" + stranicanje - ograniči na godinu dana po sync pozivu
    points = _daily_commit_counts(repo, since_ts)
    date_points = [
        (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d"), v) for ts, v in points
    ]
    return save_series(conn, "github", label, date_points)


def test_connection() -> dict:
    result = {}
    for label in REPOS:
        try:
            points = fetch_recent(label, days=14)
            total = sum(v for _, v in points)
            result[label] = {"ok": True, "message": f"{int(total)} commitova u zadnjih 14 dana"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
