"""What a discovery run was asked to cover, geographically — resolved once
from the run's config and used by every stage (query planning, listing
pages, adapters, validation) so all of them honour the SAME selection.

Why this exists: stages used to read `config.country` (only the FIRST
selected country) or the first few entries of `config.cities`, so with
several countries selected most of them were never searched, and city
queries were labelled with the wrong country ("expo in Mumbai Dubai").

Inputs, most precise first:
- `config.locations` — [{country, state?, city?}] sent by the admin UI from
  its country -> state -> city hierarchy (exact city->country mapping);
- `config.countries` / `config.country` / `config.states` / `config.cities`
  flat lists (older saved settings); a city's country is then inferred from
  the known-cities table, or from the only selected country.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from backend.services.discovery_agent.country_utils import MAJOR_CITY_TO_COUNTRY, normalize_country

_NOT_A_COUNTRY = {"", "all", "all countries", "worldwide", "global", "international", "online", "virtual"}
# Values the UI and older data use as if they were countries.
_COUNTRY_ALIASES = {"dubai": ("United Arab Emirates", "Dubai"), "abu dhabi": ("United Arab Emirates", "Abu Dhabi")}


def canonical_country(value: str | None) -> str | None:
    raw = (value or "").strip()
    if raw.lower() in _NOT_A_COUNTRY:
        return None
    if raw.lower() in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[raw.lower()][0]
    return normalize_country(raw) or None


# Spellings / metro areas that name the same place for an event search (a
# Delhi show is usually at India Expo Mart, Greater Noida, or in Gurugram).
_CITY_GROUPS = (
    ("bengaluru", "bangalore"),
    ("mumbai", "bombay", "navi mumbai"),
    ("delhi", "new delhi", "delhi ncr", "ncr", "noida", "greater noida", "gurugram", "gurgaon", "faridabad", "ghaziabad"),
    ("kolkata", "calcutta"), ("chennai", "madras"), ("hyderabad", "secunderabad"), ("pune", "poona"),
    ("dusseldorf", "duesseldorf"), ("cologne", "koln", "koeln"), ("munich", "munchen", "muenchen"),
    ("nuremberg", "nurnberg", "nuernberg"), ("frankfurt", "frankfurt am main"), ("hannover", "hanover"),
    ("ho chi minh city", "saigon", "hcmc"), ("new york", "new york city", "nyc"), ("washington", "washington dc", "washington d c"),
    ("mexico city", "ciudad de mexico"), ("saint petersburg", "st petersburg"), ("the hague", "den haag"), ("kyiv", "kiev"),
    ("beijing", "peking"), ("guangzhou", "canton"), ("milan", "milano"), ("rome", "roma"), ("vienna", "wien"), ("prague", "praha"),
    ("warsaw", "warszawa"), ("lisbon", "lisboa"), ("zurich", "zuerich"), ("geneva", "geneve", "genf"),
    ("brussels", "bruxelles", "brussel"), ("antwerp", "antwerpen"), ("gothenburg", "goteborg"), ("copenhagen", "kobenhavn"),
    ("florence", "firenze"), ("venice", "venezia"), ("turin", "torino"), ("naples", "napoli"), ("seville", "sevilla"),
    ("athens", "athina"), ("moscow", "moskva"),
)
_CITY_ALIAS = {name: group[0] for group in _CITY_GROUPS for name in group}


def city_key(value: str | None) -> str | None:
    """Comparable city name: accents and punctuation dropped, region/venue
    suffixes cut ("Mumbai, Maharashtra", "Düsseldorf / Fair ground"), and
    spelling variants / metro areas merged ("Bangalore" == "Bengaluru")."""
    import unicodedata

    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    text = re.split(r"[,/(|]| - ", text, maxsplit=1)[0]
    text = " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())
    if not text:
        return None
    return _CITY_ALIAS.get(text, text)


# Other ways sources write the states the location picker offers (native
# names, postal codes), per country — "WA" is Washington in the US but
# Western Australia in Australia.
_STATE_ALIASES: dict[str, dict[str, str]] = {
    "united states": {"ca": "california", "calif": "california", "ny": "new york", "nys": "new york", "tx": "texas", "wa": "washington",
                      "washington state": "washington", "il": "illinois", "ma": "massachusetts", "fl": "florida", "ga": "georgia", "co": "colorado"},
    "germany": {"bayern": "bavaria", "hessen": "hesse", "nordrhein westfalen": "north rhine westphalia", "nrw": "north rhine westphalia",
                "baden wuerttemberg": "baden wurttemberg", "bw": "baden wurttemberg"},
    "canada": {"on": "ontario", "bc": "british columbia", "qc": "quebec", "ab": "alberta"},
    "australia": {"nsw": "new south wales", "vic": "victoria", "qld": "queensland", "wa": "western australia"},
    "italy": {"lombardia": "lombardy", "piemonte": "piedmont", "toscana": "tuscany"},
    "spain": {"madrid": "community of madrid", "comunidad de madrid": "community of madrid", "cataluna": "catalonia", "catalunya": "catalonia",
              "andalucia": "andalusia", "comunitat valenciana": "valencian community", "comunidad valenciana": "valencian community",
              "valencia": "valencian community", "pais vasco": "basque country", "euskadi": "basque country"},
    "france": {"paca": "provence alpes cote d azur"},
    "netherlands": {"noord holland": "north holland", "zuid holland": "south holland", "noord brabant": "north brabant"},
    "switzerland": {"zh": "zurich", "geneve": "geneva", "genf": "geneva", "ge": "geneva", "vd": "vaud", "basel stadt": "basel city",
                    "basel": "basel city", "bs": "basel city", "berne": "bern", "be": "bern"},
    "brazil": {"sp": "sao paulo", "rj": "rio de janeiro", "mg": "minas gerais", "df": "federal district", "distrito federal": "federal district",
               "pr": "parana", "rs": "rio grande do sul"},
    "mexico": {"cdmx": "mexico city", "ciudad de mexico": "mexico city", "nl": "nuevo leon"},
    "south africa": {"gp": "gauteng", "wc": "western cape", "kzn": "kwazulu natal"},
    "saudi arabia": {"makkah province": "makkah", "mecca": "makkah", "ash sharqiyah": "eastern province", "riyadh province": "riyadh"},
    "united arab emirates": {"dubai emirate": "dubai", "emirate of dubai": "dubai", "emirate of abu dhabi": "abu dhabi", "rak": "ras al khaimah"},
    "india": {"nct of delhi": "delhi", "new delhi": "delhi", "delhi ncr": "delhi", "orissa": "odisha", "pondicherry": "puducherry",
              "mh": "maharashtra", "ka": "karnataka", "tn": "tamil nadu", "ts": "telangana", "up": "uttar pradesh", "gj": "gujarat"},
}


_US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california", "co": "colorado", "ct": "connecticut",
    "de": "delaware", "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland", "ma": "massachusetts", "mi": "michigan",
    "mn": "minnesota", "ms": "mississippi", "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire",
    "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee",
    "tx": "texas", "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia", "wi": "wisconsin",
    "wy": "wyoming", "dc": "district of columbia", "d c": "district of columbia",
}
_STATE_ALIASES["united states"] = {**_US_STATES, **_STATE_ALIASES["united states"]}


def known_states(country: str | None, listed: Iterable[str] = ()) -> set[str]:
    """State keys recognised for `country`: the picker's states plus the
    alias targets (all 50 US states) — anything else ("Greater London") is
    a sub-region, not evidence of being outside a ticked state."""
    aliases = _STATE_ALIASES.get((canonical_country(country) or country or "").lower(), {})
    return {state_key(s, country) for s in listed} | set(aliases.values())


def state_key(value: str | None, country: str | None = None) -> str | None:
    """Comparable state / region name for `country` (accents, punctuation,
    "State of", "Province" dropped; native names and codes merged)."""
    import unicodedata

    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    text = " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())
    text = re.sub(r"^(state of|province of)\s+|\s+(state|province)$", "", text)
    if not text:
        return None
    aliases = _STATE_ALIASES.get((canonical_country(country) or country or "").lower(), {})
    return aliases.get(text, text)


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


def _round_robin(groups: dict[str, list[str]], limit: int | None) -> list[tuple[str, str | None]]:
    queues = [(key, list(items)) for key, items in groups.items() if items]
    out: list[tuple[str, str | None]] = []
    i = 0
    while queues and (limit is None or len(out) < limit):
        i %= len(queues)
        key, items = queues[i]
        out.append((items.pop(0), key or None))
        if items:
            i += 1
        else:
            queues.pop(i)  # the next group slides into position i
    return out


@dataclass
class GeoScope:
    countries: list[str] = field(default_factory=list)
    cities_by_country: dict[str, list[str]] = field(default_factory=dict)  # "" = country unknown
    states_by_country: dict[str, list[str]] = field(default_factory=dict)  # "" = country unknown
    # States ticked WITHOUT any of their cities = the whole state.
    whole_states_by_country: dict[str, list[str]] = field(default_factory=dict)
    # The picker's state -> cities lists for those countries (sent by the UI).
    region_cities: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @property
    def worldwide(self) -> bool:
        return not self.countries and not any(self.cities_by_country.values())

    @property
    def all_cities(self) -> list[str]:
        return _dedupe(c for cities in self.cities_by_country.values() for c in cities)

    def country_of_city(self, city: str) -> str | None:
        for country, cities in self.cities_by_country.items():
            if city in cities:
                return country or None
        return None

    def fair_cities(self, limit: int | None = None) -> list[tuple[str, str | None]]:
        """(city, country) pairs taken round-robin across countries, so a cap
        never spends the whole budget on the first country's cities."""
        return _round_robin(self.cities_by_country, limit)

    def fair_states(self, limit: int | None = None) -> list[tuple[str, str | None]]:
        return _round_robin(self.states_by_country, limit)

    def anchor_places(self, limit: int | None = None) -> list[tuple[str, str | None]]:
        """(city, country) pairs to expand city-templated listing pages with:
        the selected cities, plus the major cities of every selected country
        that has none selected (so no selected country is left out), fair
        across countries. Worldwide runs use global business hubs."""
        from backend.services.discovery_agent.country_utils import cities_for_country

        groups: dict[str, list[str]] = {}
        for country in self.countries:
            groups[country] = list(self.cities_by_country.get(country) or []) or cities_for_country(country)
        if self.cities_by_country.get(""):
            groups[""] = list(self.cities_by_country[""])
        if not groups:
            hubs = ["London", "New York", "San Francisco", "Singapore", "Berlin", "Dubai", "Mumbai", "Bengaluru", "Tokyo", "Paris"]
            return [(c, MAJOR_CITY_TO_COUNTRY.get(c.lower())) for c in hubs][: limit or None]
        return _round_robin(groups, limit)

    def place_rules(self) -> dict[str, dict]:
        """{country: {"cities": ticked cities, "states": whole ticked states,
        "state_cities": that country's state -> cities list}} for every
        country with a city or state ticked. A country with neither = all of it."""
        rules = {}
        for country in self.countries:
            cities = self.cities_by_country.get(country) or []
            states = self.whole_states_by_country.get(country) or []
            if cities or states:
                rules[country] = {"cities": list(cities), "states": list(states), "state_cities": dict(self.region_cities.get(country, {}))}
        return rules

    def target_cities(self) -> dict[str, list[str]]:
        """{country: cities the admin ticked there} — only countries that have
        ticked cities; a country without any means the whole country."""
        return {country: list(cities) for country, cities in self.cities_by_country.items() if country and cities}

    def summary(self) -> dict:
        all_cities: list[str] = []
        for v in self.cities_by_country.values():
            for c in v:
                if c and c not in all_cities:
                    all_cities.append(c)
        all_states: list[str] = []
        for v in self.whole_states_by_country.values():
            for s in v:
                if s and s not in all_states:
                    all_states.append(s)
        return {
            "countries": self.countries,
            "cities": len(all_cities) if all_cities else sum(len(v) for v in self.cities_by_country.values()),
            "cities_list": all_cities,
            "target_cities": self.target_cities(),
            "states": len(all_states) if all_states else sum(len(v) for v in self.states_by_country.values()),
            "states_list": all_states,
            "worldwide": self.worldwide,
        }


def resolve(config) -> GeoScope:
    """Build the run's GeoScope from its config (see module docstring).
    Countries keep the admin's selection order; locations add any others."""
    countries: list[str] = []
    city_country: dict[str, str] = {}
    state_country: dict[str, str] = {}
    extra_cities: list[str] = []
    whole_states: dict[str, list[str]] = {}

    for raw in [*(getattr(config, "countries", None) or []), getattr(config, "country", None)]:
        country = canonical_country(raw)
        if country:
            countries.append(country)
            alias = _COUNTRY_ALIASES.get((raw or "").strip().lower())
            if alias:
                city_country.setdefault(alias[1], country)
    for loc in getattr(config, "locations", None) or []:
        country = canonical_country(loc.get("country"))
        raw_country = (loc.get("country") or "").strip().lower()
        if country:
            countries.append(country)
        city = (loc.get("city") or "").strip()
        state = (loc.get("state") or "").strip()
        if raw_country in _COUNTRY_ALIASES and not city:
            city = _COUNTRY_ALIASES[raw_country][1]  # "Dubai" selected as a country is really a city
        if city and country:
            city_country.setdefault(city, country)
        elif city:
            extra_cities.append(city)
        if state and country:
            state_country.setdefault(state, country)
            if not city:
                whole_states.setdefault(country, []).append(state)

    countries = _dedupe(countries)

    for city in getattr(config, "cities", None) or []:
        city = (city or "").strip()
        if not city or city in city_country:
            continue
        known = canonical_country(MAJOR_CITY_TO_COUNTRY.get(city.lower()))
        if known and (not countries or known in countries):
            city_country[city] = known
        elif known:
            # A city of a country the admin did not select (left over from an
            # earlier selection) — searching it would leave the chosen scope.
            continue
        elif len(countries) == 1:
            city_country[city] = countries[0]
        else:
            extra_cities.append(city)

    if not countries:
        # Cities without countries: search those cities' countries.
        countries = _dedupe(city_country.values())

    cities_by_country: dict[str, list[str]] = {c: [] for c in countries}
    for city, country in city_country.items():
        cities_by_country.setdefault(country, []).append(city)
    if extra_cities:
        cities_by_country[""] = _dedupe(extra_cities)

    states_by_country: dict[str, list[str]] = {c: [] for c in countries}
    for state in getattr(config, "states", None) or []:
        state = (state or "").strip()
        if state and state not in state_country:
            state_country[state] = countries[0] if len(countries) == 1 else ""
    for state, country in state_country.items():
        states_by_country.setdefault(country, []).append(state)

    region_cities: dict[str, dict[str, list[str]]] = {}
    for raw_country, states in (getattr(config, "region_cities", None) or {}).items():
        country = canonical_country(raw_country)
        if country and isinstance(states, dict):
            merged = region_cities.setdefault(country, {})
            for state, cities in states.items():
                merged.setdefault(state, []).extend(c for c in (cities or []) if isinstance(c, str))

    return GeoScope(
        countries=countries,
        cities_by_country={k: _dedupe(v) for k, v in cities_by_country.items()},
        states_by_country={k: _dedupe(v) for k, v in states_by_country.items() if v},
        whole_states_by_country={k: _dedupe(v) for k, v in whole_states.items() if v},
        region_cities=region_cities,
    )
