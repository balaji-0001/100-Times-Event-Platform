# Attendee Agent Documentation

## Purpose
The **Attendee Agent** (`backend/services/attendee_agent/agent.py`) discovers people actively looking for events on permitted community channels (Telegram, Discord, Reddit, Community Forums), extracts structured event intent, matches against published 100 TIMES events, and generates personalized recommendations with conversion tracking.

## Structured Intent Extraction
Given a natural language post:
> `"I want AI conferences in Hyderabad next month."`

`extract_attendee_intent()` produces:
```json
{
  "category": "AI",
  "location": "Hyderabad",
  "time_range": "next month",
  "event_type": "conference",
  "price_preference": "any",
  "format_preference": "in-person",
  "keywords": ["conferences", "Hyderabad"],
  "inferred_interests": ["AI"],
  "confidence": 0.88
}
```

## Event Matching & Relevance Scoring
`match_events_for_intent()` searches published `Event` records and computes a `0–100` relevance score based on:
- City / Location match (`+30`)
- Category match (`+25`)
- Event type / format match (`+10`)
- Keyword overlap (`+15`)
- Free/paid preference match (`+5`)

## Safety & Rate-Limit Controls
- **Per-Source Toggles (`PATCH /api/attendee-agent/sources/{source}`):** Enable or disable `telegram`, `discord`, `reddit`, or `community` independently from `/admin/attendee-agent`.
- **Daily Caps (`PlatformRateLimit`):** Prevents excessive signal processing or messaging per platform.
