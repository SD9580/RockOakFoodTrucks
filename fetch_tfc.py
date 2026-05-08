#!/usr/bin/env python3
"""
fetch_tfc.py
Pulls one week of bookings from The Food Corridor's public ganttdata endpoint
for the Clarence Creative Kitchen listing, filters to the Rock Oak Clarence
food truck calendar, and writes events.json.

Runs in GitHub Actions on a schedule. No auth required — the endpoint is public.
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LISTING_ID = "46758-clarence-creative-kitchen"
TARGET_CALENDAR = "Rock Oak Clarence [Food Trucks Only]"
USER_AGENT = "RockOakFoodTrucks-Schedule-Sync/1.0"
ENDPOINT_TEMPLATE = (
    "https://app.thefoodcorridor.com/listings/{listing}/tfc_calendars/"
    "ganttdata?date={ts}&day=1"
)
ET = ZoneInfo("America/New_York")

# Tag noise we want to strip from titles
TAG_PATTERNS_TO_STRIP = [
    " Grandfathered",
    "Grandfathered ",
    "Grandfathered",
]


def midnight_et_unix(date):
    """Return the Unix timestamp for midnight ET on the given date."""
    midnight = datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=ET)
    return int(midnight.timestamp())


def fetch_day(date):
    ts = midnight_et_unix(date)
    url = ENDPOINT_TEMPLATE.format(listing=LISTING_ID, ts=ts)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching {date}: {e}", file=sys.stderr)
        return []
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  Error fetching {date}: {e}", file=sys.stderr)
        return []


def clean_title(title):
    title = title or ""
    for pat in TAG_PATTERNS_TO_STRIP:
        title = title.replace(pat, "")
    # Collapse extra whitespace
    return " ".join(title.split())


def main():
    today = datetime.now(ET).date()
    days = [today + timedelta(days=i) for i in range(7)]

    print(f"Fetching {LISTING_ID} for {days[0]} through {days[-1]} (ET)")

    seen = set()
    events = []
    for d in days:
        raw = fetch_day(d)
        kept_today = 0
        for item in raw:
            cal = (item.get("calendar") or "").strip()
            if cal != TARGET_CALENDAR:
                continue
            title = clean_title(item.get("title", ""))
            if not title:
                continue  # Skip placeholder/empty entries
            start_ms = item.get("startDate")
            end_ms = item.get("endDate")
            if not start_ms or not end_ms or start_ms == end_ms:
                continue
            key = (start_ms, end_ms, title, cal)
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "title": title,
                "space": cal,
                "startMs": start_ms,
                "endMs": end_ms,
                "color": item.get("color") or "",
            })
            kept_today += 1
        print(f"  {d}: kept {kept_today} bookings")

    events.sort(key=lambda e: (e["startMs"], e["title"]))

    payload = {
        "events": events,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "source": "thefoodcorridor.com",
        "listingId": LISTING_ID,
        "calendarName": TARGET_CALENDAR,
    }

    with open("events.json", "w") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote events.json with {len(events)} bookings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
