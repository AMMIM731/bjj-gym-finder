"""
process_data.py

Loads the raw gym data pulled by fetch_gyms.py, cleans it into a tidy
table, and tags each gym with simple keyword themes pulled from its
reviews (e.g. "beginner_friendly", "great_instructors"). Saves the
result as gyms_clean.csv, ready for the Streamlit app.

Run with: python process_data.py
"""

import json
import pandas as pd

# Keyword themes to look for in review text. Each theme is a list of
# words/phrases — if any of them appear in a gym's combined review
# text, that gym gets tagged with the theme. This is a simple,
# explainable stand-in for full NLP sentiment analysis.
THEMES = {
    "beginner_friendly": ["beginner", "beginners", "newbie", "new to"],
    "great_instructors": ["great instructor", "great coach", "amazing instructor",
                           "knowledgeable", "excellent coach"],
    "clean_facility": ["clean", "well maintained", "hygien"],
    "good_for_kids": ["kids", "children", "my son", "my daughter"],
    "intense_competitive": ["competition", "competitive", "hardcore", "intense"],
    "friendly_community": ["friendly", "community", "family feel"],
}


def load_raw_data(path: str = "gyms_raw.json") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_review_text(gym: dict) -> str:
    """Combine all of a gym's review text into one lowercase string
    for keyword matching."""
    reviews = gym.get("reviews", [])
    texts = [r.get("text", {}).get("text", "") for r in reviews]
    return " ".join(texts).lower()


def tag_themes(review_text: str) -> list[str]:
    """Return the list of themes whose keywords appear in the review text."""
    matched = []
    for theme, keywords in THEMES.items():
        if any(keyword in review_text for keyword in keywords):
            matched.append(theme)
    return matched


def clean_gym(gym: dict) -> dict:
    """Flatten one raw Places API result into a flat row for our table."""
    review_text = extract_review_text(gym)
    location = gym.get("location", {})

    return {
        "name": gym.get("displayName", {}).get("text", "Unknown"),
        "address": gym.get("formattedAddress", ""),
        "lat": location.get("latitude"),
        "lng": location.get("longitude"),
        "rating": gym.get("rating"),
        "review_count": gym.get("userRatingCount", 0),
        "website": gym.get("websiteUri", ""),
        "phone": gym.get("internationalPhoneNumber", ""),
        "themes": ", ".join(tag_themes(review_text)),
        "review_snippet": review_text[:300],
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

    df["rating"] = df["rating"].fillna(0)
    df = df.sort_values("rating", ascending=False).reset_index(drop=True)

    df.to_csv("gyms_clean.csv", index=False)
    print(f"Saved {len(df)} cleaned gyms to gyms_clean.csv")

    print("\nTheme coverage:")
    for theme in THEMES:
        count = df["themes"].str.contains(theme).sum()
        print(f"  {theme}: {count} gyms")


if __name__ == "__main__":
    main()
