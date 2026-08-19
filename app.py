"""
app.py

Streamlit app: enter a postcode, city, or address anywhere in the
UK, France, Germany, Spain, Italy, or Canada, and find nearby BJJ
gyms sorted by distance or rating.

Originally the plan was a free-text box ("what are you looking
for?") matched against keyword-tagged review themes. That's cut —
see README.md and process_data.py for why. This version filters and
sorts on rating and review count instead, which is real data we
actually have.

Geocoding originally used postcodes.io, which only understands UK
postcodes. Now that gyms span multiple countries and continents, we
use Nominatim (OpenStreetMap's free geocoder) instead — it has no
API key, but its usage policy caps public server use at ~1
request/second and requires a descriptive User-Agent, both handled
below.

Run with: streamlit run app.py
"""

import math
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim's usage policy requires a descriptive User-Agent
# identifying the application — anonymous/default requests get
# blocked. See https://operations.osmfoundation.org/policies/nominatim/
NOMINATIM_HEADERS = {"User-Agent": "bjj-gym-finder (Streamlit demo app)"}

# Resolve gyms_clean.csv relative to this file, not the process's
# working directory — Streamlit can be launched from a different cwd
# (e.g. our preview tooling, or Streamlit Cloud's build step), and a
# bare relative path would silently break in those cases.
DATA_PATH = Path(__file__).parent / "gyms_clean.csv"

# How far to search by default. With gyms spread across five
# countries, showing every result sorted by distance would bury
# genuinely nearby ones under a long scroll of gyms in other
# cities — a radius cutoff is what makes "find a gym near me"
# actually useful.
DEFAULT_RADIUS_KM = 15


@st.cache_data
def load_gyms(path: Path = DATA_PATH, file_mtime: float = 0) -> pd.DataFrame:
    """Load gyms_clean.csv, cached until the file itself changes.

    st.cache_data keys its cache on the function's code and argument
    values, not on what a file on disk actually contains. Without
    file_mtime, a redeploy that updates gyms_clean.csv but doesn't
    touch this function's source would keep serving the previous
    deploy's cached DataFrame forever — which is exactly what
    happened on the first Europe redeploy. Passing the file's mtime
    as a plain (hashed) argument means a changed file produces a
    different cache key, busting the stale cache automatically.
    """
    return pd.read_csv(path)


def geocode_location(query: str) -> tuple[float, float] | None:
    """Look up a postcode, city, or address's lat/lng via Nominatim.

    Returns None for anything that doesn't resolve rather than
    raising — the caller decides how to show that to the user.
    """
    params = {"q": query.strip(), "format": "json", "limit": 1}
    try:
        response = requests.get(
            NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS, timeout=5
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    results = response.json()
    if not results:
        return None

    match = results[0]
    return float(match["lat"]), float(match["lon"])


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres.

    Haversine treats the Earth as a sphere, not the more accurate
    oblate spheroid. That error is centimetres at city scale — and
    results are always radius-filtered to a single metro area (30km
    max), never compared across the Atlantic — so it's not worth
    pulling in a geodesy library for this.
    """
    earth_radius_km = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return earth_radius_km * c


def add_distances(df: pd.DataFrame, origin_lat: float, origin_lng: float) -> pd.DataFrame:
    df = df.copy()
    df["distance_km"] = df.apply(
        lambda row: haversine_km(origin_lat, origin_lng, row["lat"], row["lng"]),
        axis=1,
    )
    return df


def render_gym(row: pd.Series) -> None:
    """Render one gym as a small result card."""
    badge = " 🏆 Highly rated" if row["highly_rated"] else ""
    st.markdown(f"### {row['name']}{badge}")

    if row["review_count"] > 0:
        rating_line = f"⭐ {row['rating']:.1f} ({int(row['review_count'])} reviews)"
    else:
        # Real edge case in this dataset — a handful of gyms have no
        # Google reviews at all. Showing "0.0 stars" would misread as
        # a bad gym rather than an unrated one, so we say so plainly.
        rating_line = "No reviews yet"

    st.write(f"{rating_line} · {row['distance_km']:.1f} km away")
    st.write(row["address"])

    contact_bits = []
    if row.get("website"):
        contact_bits.append(f"[Website]({row['website']})")
    if row.get("phone") and isinstance(row["phone"], str):
        contact_bits.append(row["phone"])
    if contact_bits:
        st.write(" · ".join(contact_bits))

    st.divider()


def main():
    st.set_page_config(page_title="BJJ Gym Finder — Europe & Canada", page_icon="🥋")
    st.title("🥋 BJJ Gym Finder — Europe & Canada")
    st.caption(
        "Real gym data from Google Places API (New), covering major cities in the "
        "UK, France, Germany, Spain, Italy, and Canada — one search away."
    )

    gyms = load_gyms(file_mtime=DATA_PATH.stat().st_mtime)

    location_query = st.text_input(
        "Your postcode, city, or address",
        placeholder="e.g. E1 6AN, Berlin, or Toronto, Canada",
    )

    col1, col2 = st.columns(2)
    with col1:
        radius_km = st.slider("Search radius (km)", 1, 30, DEFAULT_RADIUS_KM)
    with col2:
        sort_by = st.selectbox("Sort by", ["Distance", "Rating"])

    highly_rated_only = st.checkbox(
        "Only show highly rated gyms "
        f"(rating ≥ 4.7 with 20+ reviews)"
    )

    if not location_query:
        st.info("Enter a postcode, city, or address to see BJJ gyms near you.")
        return

    location = geocode_location(location_query)
    if location is None or location[0] is None:
        st.error(
            f"Couldn't find \"{location_query}\". "
            "Try a more specific postcode, city, or address."
        )
        return

    origin_lat, origin_lng = location
    results = add_distances(gyms, origin_lat, origin_lng)
    results = results[results["distance_km"] <= radius_km]

    if highly_rated_only:
        results = results[results["highly_rated"]]

    if sort_by == "Distance":
        results = results.sort_values("distance_km")
    else:
        results = results.sort_values(["rating", "review_count"], ascending=False)

    if results.empty:
        st.warning(
            f"No gyms found within {radius_km} km of \"{location_query}\". "
            "Try widening the search radius or clearing the "
            "highly-rated filter."
        )
        return

    st.subheader(f"{len(results)} gym(s) found")
    for _, row in results.iterrows():
        render_gym(row)


if __name__ == "__main__":
    main()
