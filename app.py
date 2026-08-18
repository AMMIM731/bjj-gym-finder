"""
app.py

Streamlit app: enter a London postcode, find nearby BJJ gyms sorted
by distance or rating.

Originally the plan was a free-text box ("what are you looking
for?") matched against keyword-tagged review themes. That's cut —
see README.md and process_data.py for why. This version filters and
sorts on rating and review count instead, which is real data we
actually have.

Run with: streamlit run app.py
"""

import math
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

POSTCODES_IO_URL = "https://api.postcodes.io/postcodes/{postcode}"

# Resolve gyms_clean.csv relative to this file, not the process's
# working directory — Streamlit can be launched from a different cwd
# (e.g. our preview tooling, or Streamlit Cloud's build step), and a
# bare relative path would silently break in those cases.
DATA_PATH = Path(__file__).parent / "gyms_clean.csv"

# How far to search by default. London is big enough that showing
# all 58 gyms sorted by distance would bury genuinely nearby ones
# under a long scroll of gyms 20km away — a radius cutoff is what
# makes "find a gym near me" actually useful.
DEFAULT_RADIUS_KM = 15


@st.cache_data
def load_gyms(path: Path = DATA_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def geocode_postcode(postcode: str) -> tuple[float, float] | None:
    """Look up a UK postcode's lat/lng via postcodes.io.

    Returns None for anything that isn't a valid, recognised postcode
    rather than raising — the caller decides how to show that to the
    user. postcodes.io is free and needs no API key, which is why we
    used it instead of another Google Geocoding call.
    """
    url = POSTCODES_IO_URL.format(postcode=postcode.strip())
    try:
        response = requests.get(url, timeout=5)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        # postcodes.io returns 404 for a well-formed but unrecognised
        # postcode, and 400 for garbage input — both mean "no result".
        return None

    result = response.json().get("result", {})
    return result.get("latitude"), result.get("longitude")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres.

    Haversine treats the Earth as a sphere, not the more accurate
    oblate spheroid. That error is centimetres at London's scale, so
    it's not worth pulling in a geodesy library for this — the
    trade-off only matters over much longer distances.
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
    st.set_page_config(page_title="BJJ Gym Finder — London", page_icon="🥋")
    st.title("🥋 BJJ Gym Finder — London")
    st.caption(
        "Real gym data from Google Places API (New), one postcode search away."
    )

    gyms = load_gyms()

    postcode = st.text_input("Your postcode", placeholder="e.g. E1 6AN")

    col1, col2 = st.columns(2)
    with col1:
        radius_km = st.slider("Search radius (km)", 1, 30, DEFAULT_RADIUS_KM)
    with col2:
        sort_by = st.selectbox("Sort by", ["Distance", "Rating"])

    highly_rated_only = st.checkbox(
        "Only show highly rated gyms "
        f"(rating ≥ 4.7 with 20+ reviews)"
    )

    if not postcode:
        st.info("Enter a postcode to see BJJ gyms near you.")
        return

    location = geocode_postcode(postcode)
    if location is None or location[0] is None:
        st.error(
            f"Couldn't find the postcode \"{postcode}\". "
            "Double check it's a real UK postcode (e.g. E1 6AN)."
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
            f"No gyms found within {radius_km} km of \"{postcode}\". "
            "Try widening the search radius or clearing the "
            "highly-rated filter."
        )
        return

    st.subheader(f"{len(results)} gym(s) found")
    for _, row in results.iterrows():
        render_gym(row)


if __name__ == "__main__":
    main()
