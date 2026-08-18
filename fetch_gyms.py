"""
fetch_gyms.py

Pulls BJJ gyms across Europe from the Google Places API (New) and
saves the raw results to gyms_raw.json.

Coverage is driven by cities.csv (built by build_city_list.py): one
text search query per city, rather than per country or per region.
Searching a named city gets far better recall from Places' Text
Search than a broad "BJJ gym in France" query would, and running one
query per city (instead of several phrasings, like the original
London-only version used) keeps this affordable at ~1,000 cities.

The field mask originally included "reviews" too, but Google's API
returns that field empty for every place regardless of field mask
syntax, sub-fields, or wildcard requests — confirmed by direct
testing (see README.md). It's dropped from the mask below since
requesting it buys nothing but a higher pricing tier.

Two-step process, per city:
  1. Text Search: cheap call that returns a list of matching places
     with basic fields (name, address, location, rating).
  2. Place Details: one call per NEW place (not already found by an
     earlier city) to get the extra fields we actually want (phone,
     website, precise review count).

This can take a while and makes a lot of billed API calls (~1,000
searches, likely several thousand detail calls). Progress is saved
incrementally to gyms_raw.json + fetch_progress.json after every
city, so an interrupted run can be resumed with the same command
instead of re-paying for cities already fetched.

Run with: python fetch_gyms.py
"""

import csv
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

# Gym names from across Europe routinely contain characters (é, ō,
# non-Latin scripts, etc.) outside Windows' default console/redirect
# encoding (cp1252), which crashes plain print() mid-run. Force UTF-8
# on stdout so this doesn't depend on how the script is invoked.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_KEY = os.environ["GOOGLE_PLACES_API_KEY"]

CITIES_CSV = "cities.csv"
OUTPUT_JSON = "gyms_raw.json"
PROGRESS_JSON = "fetch_progress.json"

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Field masks control both what data you get back AND which pricing
# tier the call falls into — only ask for what you'll actually use.
SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.userRatingCount"
)
DETAILS_FIELD_MASK = (
    "id,displayName,formattedAddress,location,rating,"
    "userRatingCount,websiteUri,internationalPhoneNumber"
)


def load_cities(path: str = CITIES_CSV) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_progress() -> dict:
    if not os.path.exists(PROGRESS_JSON):
        return {"completed_cities": [], "seen_place_ids": []}
    with open(PROGRESS_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress: dict) -> None:
    with open(PROGRESS_JSON, "w", encoding="utf-8") as f:
        json.dump(progress, f)


def load_existing_gyms() -> list[dict]:
    if not os.path.exists(OUTPUT_JSON):
        return []
    with open(OUTPUT_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_gyms(all_gyms: list[dict]) -> None:
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_gyms, f, indent=2, ensure_ascii=False)


def search_places(query: str) -> list[dict]:
    """Run one Text Search (New) query, following pagination to collect
    up to Google's cap of 60 results (3 pages of 20) per query."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
    }
    results = []
    body = {"textQuery": query, "maxResultCount": 20}

    while True:
        response = requests.post(TEXT_SEARCH_URL, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        results.extend(data.get("places", []))

        next_token = data.get("nextPageToken")
        if not next_token:
            break

        # Google requires a short delay before a new page token becomes valid.
        time.sleep(2)
        body = {"textQuery": query, "pageToken": next_token}

    return results


def get_place_details(place_id: str) -> dict:
    """Fetch full details for one place."""
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": DETAILS_FIELD_MASK,
    }
    url = DETAILS_URL.format(place_id=place_id)
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def city_key(city: dict) -> str:
    """Unique key for a cities.csv row.

    City name alone isn't unique: GeoNames lists e.g. "Latina" for
    both an Italian city and a Madrid district, and two separate
    Spanish places both named "Salamanca" (a Madrid district plus the
    actual city). Name+country isn't enough either — the two
    Salamanca rows share both. Coordinates are what actually
    distinguish them.
    """
    return f"{city['city']}|{city['country']}|{city['lat']}|{city['lng']}"


def main():
    cities = load_cities()
    progress = load_progress()
    completed_cities = set(progress["completed_cities"])
    all_gyms = load_existing_gyms()

    # Union with IDs already in gyms_raw.json, not just the progress
    # file — if fetch_progress.json is ever missing or stale (e.g. a
    # fresh clone that only kept the committed gyms_raw.json), this
    # still stops us from double-fetching and duplicating gyms already
    # saved, even though completed_cities alone can't be recovered
    # that way.
    seen_place_ids = set(progress["seen_place_ids"]) | {g["id"] for g in all_gyms}

    remaining = [c for c in cities if city_key(c) not in completed_cities]
    print(f"{len(completed_cities)}/{len(cities)} cities already done "
          f"({len(remaining)} remaining)")

    for i, city in enumerate(remaining, 1):
        query = f"Brazilian Jiu Jitsu gym in {city['city']}, {city['country']}"
        print(f"[{i}/{len(remaining)}] Searching: {query}")

        try:
            places = search_places(query)
            for place in places:
                place_id = place["id"]
                if place_id in seen_place_ids:
                    # Neighbouring cities' searches overlap sometimes.
                    continue
                seen_place_ids.add(place_id)

                name = place.get("displayName", {}).get("text", place_id)
                print(f"  Fetching details for {name}")
                details = get_place_details(place_id)
                details["source_city"] = city["city"]
                details["source_country"] = city["country"]
                all_gyms.append(details)
                time.sleep(0.2)  # be polite to the API
        except requests.RequestException as e:
            # Network hiccups shouldn't lose everything found so far —
            # save what we have and stop; re-running resumes from here.
            print(f"Error on {city['city']}: {e}")
            print("Stopping early. Re-run this script to resume.")
            break
        else:
            completed_cities.add(city_key(city))

        # Checkpoint after every city so a crash never costs more than
        # one city's worth of re-fetching.
        save_gyms(all_gyms)
        save_progress({
            "completed_cities": sorted(completed_cities),
            "seen_place_ids": sorted(seen_place_ids),
        })

    print(f"\nSaved {len(all_gyms)} gyms to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
