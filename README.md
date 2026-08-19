# BJJ Gym Finder — Europe & Canada

A small, real-data app that finds Brazilian Jiu Jitsu gyms near a
postcode, city, or address in major cities across the UK, France,
Germany, Spain, Italy, and Canada. Started as a one-day portfolio
piece covering just London, to demonstrate Python and data-handling
skills for a data analysis role — not a finished product, a
deliberately scoped-down proof of concept that was later expanded to
five countries, then to six (adding Canada) with a narrower,
major-cities-only population threshold.

## Why it's scoped this way

The original idea was bigger: a ClassPass-style app covering six
combat sports across all of London, with AI-powered search over gym
reviews ("find me a gym that's good for nervous beginners"). That's
too much for a day and, more importantly, too much to be able to
defend in detail if someone asks "why did you do it this way?" for
every part of it.

So it's cut down on three axes:

- **One sport, a population-thresholded set of cities** — BJJ only,
  and only cities of 500,000+ people across six countries (see
  `build_city_list.py`), not literally every town. Enough real data
  to be interesting, without paying for and QA-ing thousands of
  towns that almost certainly have zero BJJ gyms.
- **Keyword matching, not NLP** — see [Design decisions](#design-decisions)
  below. This was actually cut further mid-build (see
  [Known limitations](#known-limitations--what-i-cut)).
- **A working small thing beats a half-built ambitious thing.** The
  full vision is the "what I'd build next" answer in an interview,
  not something half-implemented here.

## The pipeline

```
build_city_list.py --> cities.csv --> fetch_gyms.py --> gyms_raw.json --> process_data.py --> gyms_clean.csv --> app.py
 (GeoNames filtered      (city, country,   (Google Places      (raw API          (pandas cleaning      (Streamlit,
  by population)          lat/lng list)     API, New)            responses)       + tagging)              serves the data)
```

0. **`build_city_list.py`** — Downloads GeoNames' free "cities15000"
   dataset (every city worldwide with population > 15,000) and
   filters it to the UK, France, Germany, Spain, Italy, and Canada,
   at a 500,000+ population threshold. This is what defines the
   search scope — swap the country codes or threshold at the top of
   the script to cover a different set of countries or city sizes.
   Output: `cities.csv` (50 cities at the current settings — this
   started at 50,000+ across five countries (~988 cities), then
   narrowed to major cities only when Canada was added, to keep the
   dataset focused rather than growing indefinitely with every
   expansion).

1. **`fetch_gyms.py`** — Two-step fetch against Places API (New), run
   once per city in `cities.csv`:
   - **Text Search**, one query per city (`"Brazilian Jiu Jitsu gym in
     {city}, {country}"`). One query per city — rather than the several
     phrasings the original London-only version used — keeps ~1,000
     cities affordable. Paginates through Google's 60-result cap per
     query.
   - **Place Details**, one call per unique place *not already found
     by an earlier city* (neighbouring cities' searches overlap
     sometimes), to get fields Text Search doesn't return (phone
     number, website).
   - The two-step split is deliberate: Place Details is billed per
     call, so it's wasteful to fetch full details for every result of
     every query before deduplicating. Text Search first, dedupe by
     place ID, then Details only for the gyms that survive.
   - Progress checkpoints to `fetch_progress.json` after every city,
     so an interrupted run (network blip, rate limit) can be resumed
     with the same command instead of re-paying for cities already
     done.
   - Output: `gyms_raw.json`, the raw API responses, one object per
     gym, tagged with the city/country that found it.

2. **`process_data.py`** — Loads the raw JSON, filters it down to
   only gyms whose source city is in the *current* `cities.csv`
   (see below), flattens what's left into a table with pandas, and
   computes a `highly_rated` flag (rating and review-count
   threshold — see below). Drops any gym missing lat/lng (can't be
   placed on a map or have a distance computed). Output:
   `gyms_clean.csv`.

   `gyms_raw.json` is a growing historical archive — every gym ever
   fetched, across every population threshold and country list this
   project has used, including towns below the current 500,000+ bar
   from before Canada was added. It's never pruned. This script is
   what keeps the *served* data in sync with the *current* scope
   without needing to re-fetch anything if the scope changes again:
   raising the threshold is a `build_city_list.py` + `process_data.py`
   rerun (free, no API calls); only genuinely new cities need
   `fetch_gyms.py`.

3. **`app.py`** — Streamlit app. Takes a postcode, city, or address,
   geocodes it via the free [Nominatim](https://nominatim.openstreetmap.org)
   (OpenStreetMap) API, computes distance to every gym with the
   haversine formula, and displays results filtered by radius and
   sorted by distance or rating. Nominatim replaced the original
   [postcodes.io](https://postcodes.io) integration, which only
   understands UK postcodes and couldn't geocode anywhere else —
   Nominatim needed no further changes to reach Canada, since it was
   already a global geocoder, not a Europe-specific one.

## Design decisions

**Field masks control cost, not just payload size.** Places API (New)
bills by which fields you request — the field mask isn't just "what
JSON keys do I get back", it's "what SKU tier am I paying for".
`fetch_gyms.py`'s field masks only ask for what the app actually
uses, on purpose.

**Two-step search-then-details.** Covered above — avoids paying for
Place Details on gyms that get filtered out anyway.

**Keyword matching over NLP (the original plan).** The idea was to
tag gyms with themes like `beginner_friendly` or `great_instructors`
by matching keywords against review text — simple, fully explainable,
and honest about what it can't do (see limitations below). This is
why field masks and the two-step design still read as if reviews
were part of the plan: they were, until testing showed the data
wasn't accessible. Keeping that reasoning here rather than editing
it away is deliberate — it's a more honest record of how the project
actually went.

**Rating + review count over rating alone (the fallback that shipped
instead).** Once keyword theme tagging was cut, the natural
replacement was "just use the star rating" — but the actual data
made that useless on its own: in the original 58-gym London-only
dataset, every single gym was rated 4.3 or higher. People who stick
with a combat sport for years mostly only bother reviewing gyms they
already like, so rating alone barely discriminates. Review *count*
is what actually separates "3 people loved this" from "200 people
loved this", so `highly_rated` requires both a rating threshold
(≥4.7) and a minimum review count (≥20) — see `process_data.py` for
the exact logic and reasoning in comments.

**Population-thresholded city list over an exhaustive one.**
Expanding past London raised an obvious question: search every town
in the target countries, or just the ones likely to have a BJJ gym
at all? Literally "every city" would mean thousands of Places API
calls for places that probably have zero results — BJJ gyms
concentrate in urban areas. `build_city_list.py` filters GeoNames'
city data to a population threshold instead, currently 500,000+
across six countries (50 cities). It started lower (50,000+ across
five countries, ~988 cities) and was narrowed when Canada was added,
rather than just letting the scope keep growing — a data source
that's a handful of countries' worth of major cities stays
explainable in an interview; one that's crept up to thousands of
towns across two continents doesn't.

**An archive file the served data is filtered from, not overwritten.**
When the threshold changed from 50,000+ to 500,000+, the obvious
naive approach — re-run the whole pipeline against the new
`cities.csv` — would've silently thrown away the already-paid-for
50,000+ data and only kept what the new narrower city list touches.
Instead, `fetch_gyms.py` only ever *adds* to `gyms_raw.json` (keyed
by place ID, so nothing duplicates), and `process_data.py` filters
that archive down to the current `cities.csv` scope on every run.
Net effect: narrowing the threshold cost zero API calls (all the
500,000+ cities were already-fetched subset of the 50,000+ list);
only Canada's 12 new cities needed fetching. Loosening the threshold
back down later would be free too.

## Known limitations — what I cut, and why

**Review-based keyword tagging was cut entirely.** The plan was
straightforward: pull each gym's reviews via Place Details, then tag
gyms with themes (`beginner_friendly`, `clean_facility`, etc.) by
keyword matching against the review text — a simple, explainable
stand-in for full NLP sentiment analysis.

It didn't ship, because the data wasn't there to tag. I requested
Google's `reviews` field in the Place Details field mask and got back
nothing — not an error, not an empty array, the field was just absent
from the response for every one of the 58 gyms. I investigated this
properly rather than assuming it was a quick fix:

- Confirmed it wasn't a field mask syntax issue: same empty result
  with a wildcard (`*`) mask requesting every field, and with
  explicit sub-field paths (`reviews.text`, `reviews.rating`, etc).
- Confirmed it wasn't a language/region filter: explicit
  `languageCode=en&regionCode=GB` params made no difference.
- Cross-referenced Google's own field-tier documentation: `reviews`
  sits in a distinct, higher SKU tier ("Place Details Enterprise +
  Atmosphere") than the fields that *did* come through fine
  (`rating`, `phone`, `website`, all "Enterprise" tier) — a clean,
  consistent pattern, not a random gap.
- Ruled out the obvious project-level causes: API key restrictions,
  quotas, and billing account status all checked out clean, and there
  was no matching Google status incident.
- Tried `reviewSummary` (Google's separate AI-generated review
  summary field) as a fallback text source — same result, empty.

At that point, with a one-day budget, continuing to debug an
account-level API quirk stopped being a good use of time. Rather than
ship a "themes" feature that silently tags nothing, or fake review
text to make a demo look better than the real pipeline produces, I
cut it and shipped the `highly_rated` flag instead — a smaller
feature, but one built on data that's actually real. **This is a
deliberate scope decision, not an oversight** — I'd rather defend
"I cut this and here's the evidence why" than have to defend a
feature that doesn't actually work.

**Keyword matching can't detect negation, in general.** Even had the
reviews data been accessible, this approach has a known limitation
worth stating plainly: a review saying *"not beginner friendly"*
would still match the `beginner_friendly` theme, because keyword
matching has no concept of sentence structure — it just checks
whether a substring appears anywhere in the text. Full NLP (or even
basic negation-window detection) would catch this; a one-day keyword
approach doesn't try to. That's an honest trade-off of the simple
approach, not a bug to quietly work around.

**`highly_rated` is a coarse signal.** In the original 58-gym London
dataset, 48 gyms met the threshold — it doesn't discriminate as
sharply as a more nuanced metric could (e.g. weighting recency of
reviews, or Bayesian rating). It's good enough to be a useful filter,
not good enough to be a ranking algorithm.

**No adaptive rate-limit handling.** `fetch_gyms.py` uses a flat
`time.sleep(0.2)` between Details calls rather than adaptive backoff
on 429s. Per-city checkpointing (see the pipeline section above)
covers the "run got interrupted" failure mode; it doesn't cover
"Google is actively rate-limiting us" — that would need real backoff
logic if it becomes a problem at this scale.

## Running it locally

```bash
pip install -r requirements.txt
```

Create a `.env` file with your Google Places API key:

```
GOOGLE_PLACES_API_KEY=your_key_here
```

Then run the pipeline (or skip straight to the app — `gyms_clean.csv`
is already checked in):

```bash
python build_city_list.py  # -> cities.csv (free, no API key needed)
python fetch_gyms.py       # -> gyms_raw.json (costs API calls — see below)
python process_data.py     # -> gyms_clean.csv
streamlit run app.py
```

**`fetch_gyms.py` makes billed Google Places calls** — one Text
Search per city in `cities.csv`, plus one Place Details call per
unique gym found. At the current 50-city scope that's cheap; it was
~1,000 Text Search requests plus several thousand Detail calls back
when the list covered ~988 cities at the 50,000+ threshold. Check
your Google Cloud budget/quota alerts before running it fresh with a
lowered threshold. It checkpoints after every city
(`fetch_progress.json`), so it's safe to interrupt and resume —
re-running the same command picks up where it left off instead of
re-paying for finished cities, and cities already covered by a past,
broader run are skipped automatically.

## What I'd build next

If this became the full multi-sport version:

- **Real review text.** Either resolve the Places API access issue
  (this may just need Google support, or a different billing setup)
  or bring in a second review data source, then revisit NLP-based
  theme extraction — done properly this time, with negation handling
  and a real evaluation set rather than a keyword list.
- **More sports** — the city-search pipeline already generalises;
  adding a sport is mostly a matter of changing the query template in
  `fetch_gyms.py`, not a rewrite.
- **Smaller towns, or more countries** — lower the population
  threshold or add country codes in `build_city_list.py`. Worth
  weighing against cost: dropping back to a 50,000+ threshold across
  the current six countries would mean re-fetching a long tail of
  towns unlikely to have a gym (though the ~988 cities already
  covered at that threshold before Canada was added wouldn't need
  re-fetching — see the archive-file note in Design decisions).
- **A map view**, not just a list — the lat/lng data is already
  there.
- **Caching geocoding results** and the gym dataset behind a proper
  data store instead of a CSV, once it's not just one sport in one
  city.
- **Tests** — none exist yet; for a one-day scope, manual verification
  (shown in the build process, not just claimed) stood in for a test
  suite, but a real version would need one, especially around the
  distance/filtering logic.
