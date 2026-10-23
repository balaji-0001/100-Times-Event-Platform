"""Comprehensive country utilities, standard worldwide countries dataset,
and country resolution helpers for worldwide event discovery.
"""

from urllib.parse import urlparse
import re

# Comprehensive standard list of all world countries and major territories
ALL_WORLD_COUNTRIES: list[str] = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda",
    "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas",
    "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize",
    "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil",
    "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia",
    "Cameroon", "Canada", "Central African Republic", "Chad", "Chile", "China",
    "Colombia", "Comoros", "Congo (Congo-Brazzaville)", "Costa Rica", "Croatia", "Cuba",
    "Cyprus", "Czech Republic", "Democratic Republic of the Congo", "Denmark", "Djibouti", "Dominica",
    "Dominican Republic", "Dubai", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea",
    "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France",
    "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece",
    "Grenada", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti",
    "Honduras", "Hong Kong", "Hungary", "Iceland", "India", "Indonesia",
    "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast",
    "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati",
    "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho",
    "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar",
    "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands",
    "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco",
    "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia",
    "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger",
    "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan",
    "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru",
    "Philippines", "Poland", "Portugal", "Qatar", "Romania", "Russia",
    "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "San Marino",
    "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone",
    "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa",
    "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname",
    "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia",
    "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates",
    "United Kingdom", "United States", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City",
    "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe"
]

# Aliases and ISO 3166 codes to standard name mapping
COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "gb": "United Kingdom",
    "gbr": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "in": "India",
    "ind": "India",
    "bharat": "India",
    "de": "Germany",
    "deu": "Germany",
    "deutschland": "Germany",
    "fr": "France",
    "fra": "France",
    "ca": "Canada",
    "can": "Canada",
    "au": "Australia",
    "aus": "Australia",
    "jp": "Japan",
    "jpn": "Japan",
    "sg": "Singapore",
    "sgp": "Singapore",
    "ae": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "dubai": "Dubai",
    "br": "Brazil",
    "bra": "Brazil",
    "nl": "Netherlands",
    "nld": "Netherlands",
    "holland": "Netherlands",
    "ch": "Switzerland",
    "che": "Switzerland",
    "es": "Spain",
    "esp": "Spain",
    "it": "Italy",
    "ita": "Italy",
    "ie": "Ireland",
    "irl": "Ireland",
    "nz": "New Zealand",
    "nzl": "New Zealand",
    "za": "South Africa",
    "zaf": "South Africa",
    "cn": "China",
    "chn": "China",
    "hk": "Hong Kong",
    "hkg": "Hong Kong",
    "mx": "Mexico",
    "mex": "Mexico",
    "id": "Indonesia",
    "idn": "Indonesia",
    "my": "Malaysia",
    "mys": "Malaysia",
    "th": "Thailand",
    "tha": "Thailand",
    "ph": "Philippines",
    "phl": "Philippines",
    "kr": "South Korea",
    "kor": "South Korea",
    "sa": "Saudi Arabia",
    "sau": "Saudi Arabia",
}

# Major global cities mapped to country
MAJOR_CITY_TO_COUNTRY: dict[str, str] = {
    # North America
    "new york": "United States", "san francisco": "United States", "los angeles": "United States",
    "chicago": "United States", "boston": "United States", "seattle": "United States",
    "austin": "United States", "miami": "United States", "washington": "United States",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada", "calgary": "Canada",
    "mexico city": "Mexico", "guadalajara": "Mexico", "monterrey": "Mexico",
    # Europe
    "london": "United Kingdom", "manchester": "United Kingdom", "birmingham": "United Kingdom",
    "edinburgh": "United Kingdom", "berlin": "Germany", "munich": "Germany", "frankfurt": "Germany",
    "hamburg": "Germany", "cologne": "Germany", "paris": "France", "lyon": "France",
    "marseille": "France", "amsterdam": "Netherlands", "rotterdam": "Netherlands",
    "dublin": "Ireland", "madrid": "Spain", "barcelona": "Spain", "rome": "Italy",
    "milan": "Italy", "zurich": "Switzerland", "geneva": "Switzerland", "vienna": "Austria",
    "brussels": "Belgium", "stockholm": "Sweden", "copenhagen": "Denmark", "oslo": "Norway",
    "helsinki": "Finland", "warsaw": "Poland", "lisbon": "Portugal", "athens": "Greece",
    # Asia & Middle East
    "tokyo": "Japan", "osaka": "Japan", "kyoto": "Japan", "singapore": "Singapore",
    "dubai": "Dubai", "abu dhabi": "United Arab Emirates",
    "hong kong": "Hong Kong", "seoul": "South Korea", "shanghai": "China", "beijing": "China",
    "shenzhen": "China", "bangkok": "Thailand", "kuala lumpur": "Malaysia",
    "jakarta": "Indonesia", "manila": "Philippines", "riyadh": "Saudi Arabia", "doha": "Qatar",
    "tel aviv": "Israel", "bengaluru": "India", "bangalore": "India", "mumbai": "India",
    "delhi": "India", "new delhi": "India", "hyderabad": "India", "chennai": "India",
    "kolkata": "India", "pune": "India", "ahmedabad": "India", "jaipur": "India",
    # Oceania
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia", "perth": "Australia",
    "auckland": "New Zealand", "wellington": "New Zealand",
    # Latin America
    "sao paulo": "Brazil", "rio de janeiro": "Brazil", "buenos aires": "Argentina",
    "santiago": "Chile", "bogota": "Colombia", "lima": "Peru",
    # Africa
    "johannesburg": "South Africa", "cape town": "South Africa", "nairobi": "Kenya",
    "cairo": "Egypt", "lagos": "Nigeria", "casablanca": "Morocco"
}

# Domain TLD to country
TLD_TO_COUNTRY: dict[str, str] = {
    ".uk": "United Kingdom", ".co.uk": "United Kingdom", ".org.uk": "United Kingdom",
    ".de": "Germany", ".fr": "France", ".ca": "Canada", ".au": "Australia", ".com.au": "Australia",
    ".jp": "Japan", ".co.jp": "Japan", ".in": "India", ".co.in": "India",
    ".sg": "Singapore", ".com.sg": "Singapore", ".ae": "United Arab Emirates",
    ".br": "Brazil", ".com.br": "Brazil", ".nl": "Netherlands", ".ch": "Switzerland",
    ".es": "Spain", ".it": "Italy", ".ie": "Ireland", ".nz": "New Zealand",
    ".co.nz": "New Zealand", ".za": "South Africa", ".co.za": "South Africa",
    ".cn": "China", ".hk": "Hong Kong", ".mx": "Mexico", ".se": "Sweden",
    ".no": "Norway", ".dk": "Denmark", ".fi": "Finland", ".be": "Belgium",
    ".at": "Austria", ".pl": "Poland", ".pt": "Portugal",
}


def normalize_country(value: str | None) -> str | None:
    """Normalizes raw country input into standard country name."""
    if not value:
        return None
    val = value.strip()
    if not val or val.lower() in ("all", "all countries", "worldwide", "global", "none", "null"):
        return None

    lowered = val.lower()
    if lowered in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[lowered]

    for country in ALL_WORLD_COUNTRIES:
        if country.lower() == lowered:
            return country

    # Partial / substring check
    for country in ALL_WORLD_COUNTRIES:
        if re.search(rf"\b{re.escape(country.lower())}\b", lowered):
            return country

    return val.title()


def infer_country(
    raw_country: str | None = None,
    city: str | None = None,
    state: str | None = None,
    url: str | None = None,
    default: str = "United States",
) -> str:
    """Infers standard country name from structured address, city, state or URL TLD."""
    if raw_country:
        normalized = normalize_country(raw_country)
        if normalized:
            return normalized

    if city:
        city_lower = city.strip().lower()
        if city_lower in MAJOR_CITY_TO_COUNTRY:
            return MAJOR_CITY_TO_COUNTRY[city_lower]
        for c_name, c_country in MAJOR_CITY_TO_COUNTRY.items():
            if c_name in city_lower:
                return c_country

    if url:
        try:
            host = (urlparse(url).netloc or "").lower().removeprefix("www.")
            for tld, country in TLD_TO_COUNTRY.items():
                if host.endswith(tld):
                    return country
        except Exception:
            pass

    return default


def cities_for_country(country_name: str | None) -> list[str]:
    """Returns notable cities for a given country or territory."""
    if not country_name:
        return []
    c_lower = country_name.strip().lower()
    if c_lower == "dubai":
        return ["Dubai"]
    if c_lower in ("united arab emirates", "uae"):
        return ["Dubai", "Abu Dhabi"]
    
    cities = [city.title() for city, c in MAJOR_CITY_TO_COUNTRY.items() if c.lower() == c_lower]
    return cities

