"""
process_data.py

Loads the raw gym data pulled by fetch_gyms.py and cleans it into a
tidy table, saved as gyms_clean.csv, ready for the Streamlit app.

Originally this tagged gyms with keyword themes pulled from review
text (e.g. "beginner_friendly"). That was cut: Google's Places API
(New) returned an empty "reviews" field for every single gym, even
with a wildcard field mask — confirmed by testing directly, not
assumed. See README.md for the full investigation. Rather than ship
a feature that silently does nothing, we fall back to a signal we
actually have: rating and review count.

Run with: python process_data.py
"""

import json
import pandas as pd

# A gym needs BOTH a high rating and enough reviews to be flagged.
# Rating alone barely discriminates in this dataset — nearly every
# BJJ gym in London is rated 4.3+, because people who stick with a
# combat sport for years tend to only bother reviewing gyms they
# like. Review count is what actually separates "3 people said this
# is great" from "200 people said this is great", so it does most of
# the real filtering work here.
HIGHLY_RATED_MIN_RATING = 4.7
HIGHLY_RATED_MIN_REVIEWS = 20


def load_raw_data(path: str = "gyms_raw.json") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_highly_rated(rating: float, review_count: int) -> bool:
    """A gym counts as highly rated only if enough people vouched for
    it — a 5.0 from 3 reviews isn't the same claim as a 4.9 from 200."""
    return rating >= HIGHLY_RATED_MIN_RATING and review_count >= HIGHLY_RATED_MIN_REVIEWS


def clean_gym(gym: dict) -> dict:
    """Flatten one raw Places API result into a flat row for our table."""
    location = gym.get("location", {})
    rating = gym.get("rating") or 0
    review_count = gym.get("userRatingCount") or 0

    return {
        "name": gym.get("displayName", {}).get("text", "Unknown"),
        "address": gym.get("formattedAddress", ""),
        "city": gym.get("source_city", ""),
        "country": gym.get("source_country", ""),
        "lat": location.get("latitude"),
        "lng": location.get("longitude"),
        "rating": rating,
        "review_count": review_count,
        "website": gym.get("websiteUri", ""),
        "phone": gym.get("internationalPhoneNumber", ""),
        "highly_rated": is_highly_rated(rating, review_count),
    }


def main():
    raw_gyms = load_raw_data()
    rows = [clean_gym(gym) for gym in raw_gyms]
    df = pd.DataFrame(rows)

    # Drop gyms with no usable location — can't place them on a map or
    # compute distance without one. A missing rating isn't broken data
    # though, just a genuinely new gym, so we fill it in rather than
    # dropping the row.
    before = len(df)
    df = df.dropna(subset=["lat", "lng"])
    dropped = before - len(df)
    if dropped:
        print(f"Dropped {dropped} gym(s) with missing location data")

    # Rating first, review count as the tiebreaker — lots of gyms
    # share the same rating (see README), so count is what actually
    # orders them meaningfully.
    df = df.sort_values(["rating", "review_count"], ascending=False).reset_index(drop=True)

    df.to_csv("gyms_clean.csv", index=False)
    print(f"Saved {len(df)} cleaned gyms to gyms_clean.csv")

    highly_rated_count = df["highly_rated"].sum()
    print(f"\nHighly rated (rating >= {HIGHLY_RATED_MIN_RATING}, "
          f"{HIGHLY_RATED_MIN_REVIEWS}+ reviews): {highly_rated_count}/{len(df)} gyms")


if __name__ == "__main__":
    main()
