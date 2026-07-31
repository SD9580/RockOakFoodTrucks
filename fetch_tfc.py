#!/usr/bin/env python3
"""
fetch_tfc.py
Pulls one week of bookings from The Food Corridor's public ganttdata endpoint
for the Clarence Creative Kitchen listing, filters to all "[Food Trucks Only]"
calendars, and writes events.json.

The output includes every food-truck booking with the venue name preserved
in the `space` field, so different HTML pages can filter to different venues.

Runs in GitHub Actions on a schedule. No auth required — the endpoint is public.
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LISTING_ID = "46758-clarence-creative-kitchen"
FOOD_TRUCK_SUFFIX = "[Food Trucks Only]"
USER_AGENT = "RockOakFoodTrucks-Schedule-Sync/1.1"
ENDPOINT_TEMPLATE = (
    "https://app.thefoodcorridor.com/listings/{listing}/tfc_calendars/"
    "ganttdata?date={ts}&day=1"
)
ET = ZoneInfo("America/New_York")

TAG_PATTERNS_TO_STRIP = [
    " Grandfathered",
    "Grandfathered ",
    "Grandfathered",
]


def midnight_et_unix(date):
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
    return " ".join(title.split())


def main():
    today = datetime.now(ET).date()
    days = [today + timedelta(days=i) for i in range(7)]

    print(f"Fetching {LISTING_ID} for {days[0]} through {days[-1]} (ET)")

    seen = set()
    events = []
    venues_seen = set()

    for d in days:
        raw = fetch_day(d)
        kept_today = 0
        for item in raw:
            cal = (item.get("calendar") or "").strip()
            # Keep any food-truck calendar (Rock Oak or the other venues)
            if FOOD_TRUCK_SUFFIX not in cal:
                continue
            venues_seen.add(cal)

            title = clean_title(item.get("title", ""))
            if not title:
                continue
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
                "space": cal,  # Full venue name preserved for downstream filtering
                "startMs": start_ms,
                "endMs": end_ms,
                "color": item.get("color") or "",
            })
            kept_today += 1
        print(f"  {d}: kept {kept_today} bookings")

    events.sort(key=lambda e: (e["startMs"], e["space"], e["title"]))

    payload = {
        "events": events,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "source": "thefoodcorridor.com",
        "listingId": LISTING_ID,
        "venuesSeen": sorted(venues_seen),
    }

    with open("events.json", "w") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote events.json with {len(events)} bookings across {len(venues_seen)} venues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
