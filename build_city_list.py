"""
build_city_list.py

Downloads GeoNames' free "cities15000" dataset (every city worldwide
with population > 15,000) and filters it down to the countries and
population threshold we actually want to search for gyms, saving the
result to cities.csv.

Searching literally every town in Europe would be both slow and
expensive (thousands of Places API calls for places that likely have
zero BJJ gyms). Filtering by population keeps the search focused on
places actually likely to have a gym, while staying free and
reproducible — GeoNames needs no API key or account.

Run with: python build_city_list.py
"""

import csv
import io
import zipfile

import requests

GEONAMES_URL = "https://download.geonames.org/export/dump/cities15000.zip"

# ISO 3166-1 alpha-2 codes.
COUNTRIES = {
    "GB": "United Kingdom",
    "FR": "France",
    "DE": "Germany",
    "ES": "Spain",
    "IT": "Italy",
}

MIN_POPULATION = 50_000

# GeoNames' cities15000.txt is tab-separated with no header row.
# Column order: https://download.geonames.org/export/dump/readme.txt
COL_NAME = 1
COL_LATITUDE = 4
COL_LONGITUDE = 5
COL_COUNTRY_CODE = 8
COL_POPULATION = 14


def download_geonames_data() -> str:
    response = requests.get(GEONAMES_URL, timeout=30)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        return zf.read("cities15000.txt").decode("utf-8")


def filter_cities(raw_text: str) -> list[dict]:
    cities = []
    reader = csv.reader(io.StringIO(raw_text), delimiter="\t")
    for row in reader:
        country_code = row[COL_COUNTRY_CODE]
        if country_code not in COUNTRIES:
            continue

        population = int(row[COL_POPULATION]) if row[COL_POPULATION] else 0
        if population < MIN_POPULATION:
            continue

        cities.append({
            "city": row[COL_NAME],
            "country": COUNTRIES[country_code],
            "lat": row[COL_LATITUDE],
            "lng": row[COL_LONGITUDE],
            "population": population,
        })

    return cities


def main():
    print(f"Downloading city data from {GEONAMES_URL}")
    raw_text = download_geonames_data()

    cities = filter_cities(raw_text)
    cities.sort(key=lambda c: (c["country"], -c["population"]))

    with open("cities.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["city", "country", "lat", "lng", "population"])
        writer.writeheader()
        writer.writerows(cities)

    print(f"Saved {len(cities)} cities (population >= {MIN_POPULATION:,}) to cities.csv")
    for code, name in COUNTRIES.items():
        count = sum(1 for c in cities if c["country"] == name)
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
