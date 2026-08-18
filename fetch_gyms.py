"""
fetch_gyms.py

Pulls BJJ gyms in London from the Google Places API (New) and saves
the raw results to gyms_raw.json.

The field mask originally included "reviews" too, but Google's API
returns that field empty for every place regardless of field mask
syntax, sub-fields, or wildcard requests — confirmed by direct
testing (see README.md). It's dropped from the mask below since
requesting it buys nothing but a higher pricing tier.

Two-step process:
  1. Text Search: cheap call that returns a list of matching places
     with basic fields (name, address, location, rating).
  2. Place Details: one call per place to get the extra fields we
     actually want (phone, website, precise review count).

We split it this way deliberately — pulling Place Details for every
result up front would be wasteful if a search query returns places
we don't care about, since Details is billed per call.

Run with: python fetch_gyms.py
"""

import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["GOOGLE_PLACES_API_KEY"]

# Different phrasing and area terms surface different gyms — add more
# here later for other sports.
SEARCH_QUERIES = [
    "BJJ gym in London",
    "Brazilian Jiu Jitsu club London",
    "Jiu Jitsu academy London",
    "BJJ gym North London",
    "BJJ gym South London",
    "BJJ gym East London",
    "BJJ gym West London",
]

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


def main():
    seen_ids = set()
    all_gyms = []

    for query in SEARCH_QUERIES:
        print(f"Searching: {query}")
        for place in search_places(query):
            place_id = place["id"]
            if place_id in seen_ids:
                # The two queries overlap on some gyms — skip duplicates.
                continue
            seen_ids.add(place_id)

            name = place.get("displayName", {}).get("text", place_id)
            print(f"  Fetching details for {name}")
            details = get_place_details(place_id)
            all_gyms.append(details)
            time.sleep(0.2)  # be polite to the API

    with open("gyms_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_gyms, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_gyms)} gyms to gyms_raw.json")


if __name__ == "__main__":
    main()
