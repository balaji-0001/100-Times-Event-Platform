"""Rule-based event categorization (no AI). Cases are real event titles the
discovery automation found."""

import pytest

from backend.services.discovery_agent.categorizer import CATEGORIES, categorize


@pytest.mark.parametrize("name, category, event_type", [
    ("Global Pharma Innovations Summit", "Pharmaceuticals", "Summit"),
    ("Drug Formulation & Vaccine Development Workshop", "Pharmaceuticals", "Workshop"),
    ("Healthcare Quality and Hospital Management Conclave", "Healthcare", "Conference"),
    ("International Medical Science & Genome Research Congress", "Healthcare", "Conference"),
    ("Renewable Energy & Solar Power Generation Expo", "Energy and Power Generation", "Exhibition"),
    ("5G Networks & Telecommunications Summit", "Telecommunications", "Summit"),
    ("Infrastructure & Civil Construction Conclave", "Construction", "Conference"),
    ("Future of Mining & Mineral Extraction Summit", "Mining", "Summit"),
    ("Global Banking & Fintech Investment Conference", "Finance", "Conference"),
    ("Sustainable Packaging Machinery Expo", "Packaging", "Exhibition"),
    ("Transport & Freight Logistics Conclave", "Transport and Logistics", "Conference"),
    ("Oil & Gas Pipeline Technology Expo", "Oil and Gas", "Exhibition"),
    ("Global Textile & Fabric Weaving Fair", "Textiles", "Exhibition"),
    ("Advanced Robotics & Industrial Manufacturing Expo", "Manufacturing", "Exhibition"),
    ("Random Unmatched Event Name 2026", "Other", None),
])
def test_real_titles(name, category, event_type):
    assert categorize(name) == (category, event_type)


@pytest.mark.parametrize("name, category", [
    # A generic "technology" must not outrank the sector the event is about.
    ("Offshore Technology Conference (OTC) 2027", "Oil and Gas"),
    ("SPE Hydraulic Fracturing Technology Conference & Exhibition", "Oil and Gas"),
    ("Construction Technology Summit 2027", "Construction"),
    ("Building Technology Expo", "Construction"),
    ("Healthcare Technology Conference", "Healthcare"),
    ("Oil & Gas Trade Shows in India", "Oil and Gas"),
    ("India Energy Week 2027", "Energy and Power Generation"),
    ("GREEN ENERGY INDIA EXPO 2026", "Energy and Power Generation"),
    ("2027 IEEE South Asia Power Electronics Conference", "Energy and Power Generation"),
    ("Pub Crawls in Dubai: Nightlife Tours", "Other"),
    ("AI & Cloud Summit", "Technology"),
    # Off-sector consumer events found by city listing pages.
    ("Music Performance by ADIGA", "Other"),
    ("Georgia Country Trip", "Other"),
    ("SoMAD Halloween Carnival 2026", "Other"),
])
def test_sector_beats_generic_technology(name, category):
    assert categorize(name)[0] == category


def test_description_decides_when_the_name_has_no_keywords():
    assert categorize("Sobo Evenings", "An evening of sustainable packaging machinery networking")[0] == "Packaging"


def test_short_words_need_whole_word_matches():
    # "=api" must match whole word, not inside "capital"
    assert categorize("Venture Capital Conference")[0] == "Finance"


def test_every_result_is_in_the_category_list():
    for name in ("Pharma Expo", "Power Grid Conclave", "Textile Weaving Summit", "Robotics Manufacturing Forum"):
        assert categorize(name)[0] in CATEGORIES

