---
title: MakeMyTrip Autonomous Agent
emoji: ✈️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# ✈️ MakeMyTrip Autonomous Web Agent

A Streamlit app where an AI browser agent (**browser-use + Google Gemini**) searches MakeMyTrip for you and shows the results in clean tables.

## Features

- 9 services: Flights, Trains, Buses, Cabs, Hotels, Villas & Homestays, Attractions, Holiday Packages, Cruises
- Single-date search, multi-date comparison, and "cheapest fare per date" view for flights
- Travellers step (adults, children, infants, rooms)
- Fare trend chart, top-5 cheapest dates, CSV download
- Animated travel-themed UI

## Tech stack

Python · Streamlit · browser-use · Playwright (Chromium) · Google Gemini · pandas

## Run locally

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac / Linux

pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file in the project folder:

```
GOOGLE_API_KEY=your_gemini_api_key
```

Start the app:

```bash
streamlit run app.py
```

## Deploy (Hugging Face Spaces, Docker)

1. Create a new Space, choose **Docker** as the SDK.
2. Push this repo to the Space.
3. In **Settings → Variables and secrets**, add a **Secret** named `GOOGLE_API_KEY`.
4. The Space builds the `Dockerfile` and starts the app on port 7860.

## Notes

- Each search takes about 1-2 minutes because a real browser is automated.
- Gemini free tier has rate limits (429 errors are possible on heavy use).
- Results are saved in `results/` (temporary on cloud hosting).
- Built for learning/demo purposes. Respect the terms of service of the websites you automate.
