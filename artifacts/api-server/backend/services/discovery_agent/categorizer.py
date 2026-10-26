"""Rule-based event categorization — fixed keyword lists, no AI.

`categorize(name, description, url)` returns (category, event_type):
- category: one of `CATEGORIES`. Keywords in the event name count 3x, in
  the description/URL 1x; the highest score wins, ties go to the category
  listed first in `_PRIORITY`, and no match at all is "Other".
- event_type: Conference / Summit / Workshop / Meetup / … or None — stored
  in `DiscoveredEvent.subcategory`.

Keyword syntax: "word" matches at the start of a word ("startup" also
matches "startups"), "=word" only as a whole word (for short words like
"ai"), "~word" anywhere, even inside a compound ("~food" in "Indusfood").
"""

import re

CATEGORIES = (
    "Pharmaceuticals",
    "Healthcare",
    "Energy and Power Generation",
    "Telecommunications",
    "Construction",
    "Mining",
    "Finance",
    "Packaging",
    "Transport and Logistics",
    "Oil and Gas",
    "Textiles",
    "Manufacturing",
    "Technology",
    "Other",
)

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Technology": (
        "tech", "technology", "software", "computing", "developer", "coding", "ai", "cloud", "data", "cyber",
        "hackathon", "machine learning", "devops", "web3", "digital", "deep learning", "nlp", "iot", "robotics",
        "=api", "=apis", "rest api", "microservice", "javascript", "python", "golang", "kubernetes", "fullstack",
    ),
    "Pharmaceuticals": (
        "pharma", "pharmaceutic", "drug discover", "drug manufactur", "clinical trial", "active pharmaceutical ingredient", "pharma api",
        "biosimilar", "formulation", "pharmacolog", "vaccine", "biopharma", "generic drug", "biotech",
    ),
    "Healthcare": (
        "healthcare", "=hospital", "=hospitals", "health", "healthtech", "telehealth", "patient care", "nursing",
        "digital health", "clinic", "health system", "medical device", "wellness", "doctor",
        "medical science", "medicine", "biomedical", "genom", "patholog", "cardio", "oncolog",
        "neurolog", "pediatric", "radiolog", "surgery", "surgical", "immunolog", "clinical research",
        "crispr", "genetics", "life science", "medical", "dental", "pharma",
    ),
    "Energy and Power Generation": (
        "power generation", "renewable energy", "clean energy", "energy transition", "energy summit", "energy conference", "solar", "wind energy", "thermal power",
        "hydropower", "clean energy", "electricity", "power plant", "grid", "smart grid", "battery storage",
        "nuclear power", "power grid", "photovoltaic", "ev", "electric vehicle",
    ),
    "Telecommunications": (
        "telecom", "telecommunication", "=5g", "=6g", "wireless", "broadband", "optical fiber",
        "network", "satellite", "operator", "spectrum", "cellular", "enterprise it", "cloud telecom", "=voip",
    ),
    "Construction": (
        "construction", "infrastructure", "civil engineering", "civilengineer", "civil engineer", "builder", "building technology", "contech",
        "cement", "concrete", "smart cities", "architecture", "highway", "bridge", "urban planning",
        "real estate development", "property", "real estate", "proptech", "interior design", "housing", "architect",
    ),
    "Mining": (
        "mining", "mineral", "extraction", "ore", "coal mining", "gold mining", "iron ore", "quarry",
        "drilling", "metallurg", "geology", "smelting", "mine safety",
    ),
    "Finance": (
        "finance", "fintech", "banking", "=bank", "invest", "investment", "capital markets", "wealth",
        "asset management", "insurance", "insurtech", "private equity", "venture capital", "accounting",
        "=tax", "stock market", "mutual fund", "trade", "trading", "startup", "entrepreneur", "founder", "pitch", "business", "commerce",
    ),
    "Packaging": (
        "packaging", "packtech", "packmach", "packplus", "propak", "corrugated", "flexible packaging", "carton", "bottling", "labeling",
        "sustainable packaging", "food packaging", "blister pack", "container", "packaging machinery",
    ),
    "Transport and Logistics": (
        "transport", "logistics", "supply chain", "freight", "cargo", "shipping", "railway", "aviation",
        "airline", "maritime", "=port", "fleet", "warehouse", "warehousing", "cold chain", "trucking", "mobility", "automotive", "vehicle",
    ),
    "Oil and Gas": (
        "oil and gas", "oilandgas", "petroleum", "upstream", "downstream", "refinery", "pipeline", "drilling",
        "crude oil", "natural gas", "=lng", "=lpg", "petrochemical", "offshore", "hydrocarbon",
    ),
    "Textiles": (
        "textile", "fabric", "garment", "apparel", "spinning", "weaving", "yarn", "cotton",
        "fashion technology", "fiber", "dyeing", "loom", "technical textile", "fashion",
    ),
    "Manufacturing": (
        "manufacturing", "industrial", "industry 4.0", "machinery", "automation", "robotics", "=cnc",
        "tooling", "casting", "forging", "factory", "assembly line", "smart manufacturing", "precision engineering",
        "autotech", "autotechnicia", "metalworking", "food processing", "beverage", "food", "foodtech",
    ),
}

# Tie-break order: more specific categories first.
_PRIORITY = (
    "Technology",
    "Pharmaceuticals",
    "Healthcare",
    "Energy and Power Generation",
    "Oil and Gas",
    "Telecommunications",
    "Construction",
    "Mining",
    "Packaging",
    "Transport and Logistics",
    "Textiles",
    "Manufacturing",
    "Finance",
)

_EVENT_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Hackathon", ("hackathon",)),
    ("Conference", ("conference", "conclave", "congress", "symposium", "forum")),
    ("Summit", ("summit",)),
    ("Workshop", ("workshop", "bootcamp", "masterclass", "master class", "hands-on", "training")),
    ("Webinar", ("webinar", "online session")),
    ("Meetup", ("meetup", "meet-up", "meet up")),
    ("Exhibition", ("exhibition", "=expo", "trade show", "trade fair", "=fair", "auto show")),
    ("Festival", ("festival", "=fest", "~utsav", "~otsav", "=mela", "=puja", "=pooja", "navratri", "~garba", "~dandiya", "carnival")),
    ("Concert", ("concert", "=gig", "=live in", "=live at")),
    ("Seminar", ("seminar", "information session", "info session", "lecture", "=talk", "=fdp", "panel discussion")),
    ("Networking", ("networking", "mixer")),
    ("Competition", ("competition", "contest", "tournament", "championship", "marathon", "olympiad")),
    ("Awards", ("awards",)),
    ("Party", ("party", "parties")),
)

# "PyCon", "FlutterCon", "DevCon" are conferences; these words merely end in "con".
_CON_SUFFIX = re.compile(r"\b[a-z]{2,}con\b")
_NOT_CONFERENCES = {"silicon", "falcon", "bacon", "icon", "beacon", "deacon", "lexicon", "tycoon", "recon", "deccan"}


def _pattern(keyword: str) -> re.Pattern:
    if keyword.startswith("="):
        return re.compile(rf"\b{re.escape(keyword[1:])}\b")
    if keyword.startswith("~"):
        return re.compile(re.escape(keyword[1:]))
    return re.compile(rf"\b{re.escape(keyword)}")


_CATEGORY_PATTERNS = {category: [_pattern(k) for k in keywords] for category, keywords in _KEYWORDS.items()}
_TYPE_PATTERNS = [(event_type, [_pattern(k) for k in keywords]) for event_type, keywords in _EVENT_TYPES]


def get_supported_categories(db: object | None = None) -> list[str]:
    """Dynamically retrieves all categories currently listed in 100 TIMES database.
    Falls back to CATEGORIES if DB is unavailable."""
    if db is not None:
        try:
            from sqlalchemy import select
            from backend.models import Category
            cats = [c for c in db.execute(select(Category.name).order_by(Category.name)).scalars().all() if c]
            if cats:
                return cats
        except Exception:
            pass
    return [c for c in CATEGORIES if c != "Other"]


def _patterns_for_category(category: str) -> list[re.Pattern]:
    if category in _CATEGORY_PATTERNS:
        return _CATEGORY_PATTERNS[category]
    # Dynamically generate token patterns for newly created categories
    words = [w.lower() for w in re.split(r"[^a-zA-Z0-9]+", category) if len(w) > 2]
    keywords = [category.lower()]
    for w in words:
        if w not in ("and", "the", "for", "with", "all"):
            keywords.append(w)
    return [_pattern(k) for k in keywords]


def categorize(
    name: str | None,
    description: str | None = None,
    url: str | None = None,
    supported_categories: list[str] | tuple[str, ...] | None = None,
    db: object | None = None,
) -> tuple[str, str | None]:
    title = (name or "").lower()
    context = " ".join(filter(None, [description, url])).lower().replace("-", " ").replace("/", " ")

    valid_categories = list(supported_categories) if supported_categories is not None else get_supported_categories(db)
    priority = [c for c in _PRIORITY if c in valid_categories] + [c for c in valid_categories if c not in _PRIORITY]

    scores: dict[str, int] = {}
    for cat in valid_categories:
        patterns = _patterns_for_category(cat)
        score = sum(3 for p in patterns if p.search(title)) + sum(1 for p in patterns if p.search(context))
        if score > 0:
            scores[cat] = score

    if scores:
        category = max(priority, key=lambda c: (scores.get(c, 0), -priority.index(c)))
    else:
        category = "Other"

    return category, _event_type(title) or _event_type(context)


def _event_type(text: str) -> str | None:
    if not text:
        return None
    for event_type, patterns in _TYPE_PATTERNS:
        if any(p.search(text) for p in patterns):
            return event_type
    if any(word not in _NOT_CONFERENCES for word in _CON_SUFFIX.findall(text)):
        return "Conference"
    return None
