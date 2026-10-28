/**
 * Standard list of all world countries (ISO 3166-1 standard sovereign states & territories)
 * for worldwide event discovery and country-level filtering.
 */

export const ALL_WORLD_COUNTRIES: string[] = [
  'Afghanistan', 'Albania', 'Algeria', 'Andorra', 'Angola', 'Antigua and Barbuda',
  'Argentina', 'Armenia', 'Australia', 'Austria', 'Azerbaijan', 'Bahamas',
  'Bahrain', 'Bangladesh', 'Barbados', 'Belarus', 'Belgium', 'Belize',
  'Benin', 'Bhutan', 'Bolivia', 'Bosnia and Herzegovina', 'Botswana', 'Brazil',
  'Brunei', 'Bulgaria', 'Burkina Faso', 'Burundi', 'Cabo Verde', 'Cambodia',
  'Cameroon', 'Canada', 'Central African Republic', 'Chad', 'Chile', 'China',
  'Colombia', 'Comoros', 'Congo (Congo-Brazzaville)', 'Costa Rica', 'Croatia', 'Cuba',
  'Cyprus', 'Czech Republic', 'Democratic Republic of the Congo', 'Denmark', 'Djibouti', 'Dominica',
  'Dominican Republic', 'Dubai', 'Ecuador', 'Egypt', 'El Salvador', 'Equatorial Guinea', 'Eritrea',
  'Estonia', 'Eswatini', 'Ethiopia', 'Fiji', 'Finland', 'France',
  'Gabon', 'Gambia', 'Georgia', 'Germany', 'Ghana', 'Greece',
  'Grenada', 'Guatemala', 'Guinea', 'Guinea-Bissau', 'Guyana', 'Haiti',
  'Honduras', 'Hong Kong', 'Hungary', 'Iceland', 'India', 'Indonesia',
  'Iran', 'Iraq', 'Ireland', 'Israel', 'Italy', 'Ivory Coast',
  'Jamaica', 'Japan', 'Jordan', 'Kazakhstan', 'Kenya', 'Kiribati',
  'Kuwait', 'Kyrgyzstan', 'Laos', 'Latvia', 'Lebanon', 'Lesotho',
  'Liberia', 'Libya', 'Liechtenstein', 'Lithuania', 'Luxembourg', 'Madagascar',
  'Malawi', 'Malaysia', 'Maldives', 'Mali', 'Malta', 'Marshall Islands',
  'Mauritania', 'Mauritius', 'Mexico', 'Micronesia', 'Moldova', 'Monaco',
  'Mongolia', 'Montenegro', 'Morocco', 'Mozambique', 'Myanmar', 'Namibia',
  'Nauru', 'Nepal', 'Netherlands', 'New Zealand', 'Nicaragua', 'Niger',
  'Nigeria', 'North Korea', 'North Macedonia', 'Norway', 'Oman', 'Pakistan',
  'Palau', 'Palestine', 'Panama', 'Papua New Guinea', 'Paraguay', 'Peru',
  'Philippines', 'Poland', 'Portugal', 'Qatar', 'Romania', 'Russia',
  'Rwanda', 'Saint Kitts and Nevis', 'Saint Lucia', 'Saint Vincent and the Grenadines', 'Samoa', 'San Marino',
  'Sao Tome and Principe', 'Saudi Arabia', 'Senegal', 'Serbia', 'Seychelles', 'Sierra Leone',
  'Singapore', 'Slovakia', 'Slovenia', 'Solomon Islands', 'Somalia', 'South Africa',
  'South Korea', 'South Sudan', 'Spain', 'Sri Lanka', 'Sudan', 'Suriname',
  'Sweden', 'Switzerland', 'Syria', 'Taiwan', 'Tajikistan', 'Tanzania',
  'Thailand', 'Timor-Leste', 'Togo', 'Tonga', 'Trinidad and Tobago', 'Tunisia',
  'Turkey', 'Turkmenistan', 'Tuvalu', 'Uganda', 'Ukraine', 'United Arab Emirates',
  'United Kingdom', 'United States', 'Uruguay', 'Uzbekistan', 'Vanuatu', 'Vatican City',
  'Venezuela', 'Vietnam', 'Yemen', 'Zambia', 'Zimbabwe'
];

/**
 * Standard hierarchy of States and Notable Cities for major countries.
 * Country -> State/Region -> Array of Cities
 */
export const COUNTRY_HIERARCHY: Record<string, Record<string, string[]>> = {
  'India': {
    'Andhra Pradesh': ['Visakhapatnam', 'Vijayawada', 'Guntur', 'Tirupati', 'Kakinada', 'Nellore', 'Rajahmundry', 'Kurnool'],
    'Arunachal Pradesh': ['Itanagar', 'Tawang', 'Pasighat', 'Ziro'],
    'Assam': ['Guwahati', 'Silchar', 'Dibrugarh', 'Jorhat', 'Tezpur', 'Nagaon'],
    'Bihar': ['Patna', 'Gaya', 'Bhagalpur', 'Muzaffarpur', 'Darbhanga', 'Purnia'],
    'Chandigarh': ['Chandigarh'],
    'Chhattisgarh': ['Raipur', 'Bhilai', 'Bilaspur', 'Korba', 'Durg'],
    'Delhi': ['New Delhi', 'Delhi', 'North Delhi', 'South Delhi', 'East Delhi', 'West Delhi', 'Dwarka'],
    'Goa': ['Panaji', 'Margao', 'Vasco da Gama', 'Mapusa', 'Ponda'],
    'Gujarat': ['Ahmedabad', 'Surat', 'Vadodara', 'Rajkot', 'Gandhinagar', 'Bhavnagar', 'Jamnagar', 'Junagadh'],
    'Haryana': ['Gurugram', 'Faridabad', 'Panipat', 'Ambala', 'Karnal', 'Hisar', 'Rohtak', 'Panchkula'],
    'Himachal Pradesh': ['Shimla', 'Dharamshala', 'Solan', 'Mandi', 'Kullu', 'Manali'],
    'Jammu and Kashmir': ['Srinagar', 'Jammu', 'Anantnag', 'Baramulla'],
    'Jharkhand': ['Ranchi', 'Jamshedpur', 'Dhanbad', 'Bokaro', 'Deoghar'],
    'Karnataka': ['Bengaluru', 'Mysuru', 'Hubballi', 'Mangaluru', 'Belagavi', 'Davanagere', 'Ballari', 'Kalaburagi'],
    'Kerala': ['Kochi', 'Thiruvananthapuram', 'Kozhikode', 'Thrissur', 'Kollam', 'Palakkad', 'Kannur', 'Alappuzha'],
    'Ladakh': ['Leh', 'Kargil'],
    'Madhya Pradesh': ['Bhopal', 'Indore', 'Gwalior', 'Jabalpur', 'Ujjain', 'Sagar', 'Dewas'],
    'Maharashtra': ['Mumbai', 'Pune', 'Nagpur', 'Aurangabad', 'Nashik', 'Thane', 'Navi Mumbai', 'Solapur', 'Kolhapur', 'Amravati'],
    'Manipur': ['Imphal', 'Churachandpur'],
    'Meghalaya': ['Shillong', 'Tura', 'Jowai'],
    'Mizoram': ['Aizawl', 'Lunglei'],
    'Nagaland': ['Kohima', 'Dimapur'],
    'Odisha': ['Bhubaneswar', 'Cuttack', 'Rourkela', 'Puri', 'Sambalpur', 'Berhampur'],
    'Puducherry': ['Puducherry', 'Karaikal', 'Oulgaret'],
    'Punjab': ['Ludhiana', 'Amritsar', 'Jalandhar', 'Patiala', 'Bathinda', 'Mohali'],
    'Rajasthan': ['Jaipur', 'Jodhpur', 'Udaipur', 'Kota', 'Ajmer', 'Bikaner', 'Bhilwara', 'Alwar'],
    'Sikkim': ['Gangtok', 'Namchi'],
    'Tamil Nadu': ['Chennai', 'Coimbatore', 'Madurai', 'Tiruchirappalli', 'Salem', 'Tirunelveli', 'Erode', 'Vellore'],
    'Telangana': ['Hyderabad', 'Warangal', 'Nizamabad', 'Karimnagar', 'Khammam', 'Secunderabad', 'Ramagundam'],
    'Tripura': ['Agartala', 'Udaipur'],
    'Uttar Pradesh': ['Lucknow', 'Noida', 'Greater Noida', 'Kanpur', 'Varanasi', 'Agra', 'Prayagraj', 'Ghaziabad', 'Meerut', 'Bareilly', 'Aligarh'],
    'Uttarakhand': ['Dehradun', 'Haridwar', 'Roorkee', 'Haldwani', 'Rishikesh', 'Nainital'],
    'West Bengal': ['Kolkata', 'Howrah', 'Durgapur', 'Asansol', 'Siliguri', 'Bardhaman'],
  },
  'Dubai': {
    'Dubai Emirate': ['Dubai', 'Downtown Dubai', 'Business Bay', 'Deira', 'Bur Dubai', 'Dubai Marina', 'Jumeirah', 'Palm Jumeirah', 'DIFC'],
  },
  'United Arab Emirates': {
    'Dubai': ['Dubai', 'Downtown Dubai', 'Business Bay', 'Deira', 'Bur Dubai', 'Dubai Marina', 'Jumeirah'],
    'Abu Dhabi': ['Abu Dhabi', 'Al Ain', 'Al Dhafra'],
    'Sharjah': ['Sharjah', 'Khor Fakkan', 'Kalba'],
    'Ajman': ['Ajman'],
    'Ras Al Khaimah': ['Ras Al Khaimah'],
    'Fujairah': ['Fujairah'],
    'Umm Al Quwain': ['Umm Al Quwain'],
  },
  'United States': {
    'California': ['San Francisco', 'Los Angeles', 'San Diego', 'San Jose', 'Sacramento', 'Oakland', 'Palo Alto', 'Mountain View', 'Irvine'],
    'New York': ['New York', 'Brooklyn', 'Manhattan', 'Buffalo', 'Rochester', 'Albany', 'Syracuse'],
    'Texas': ['Austin', 'Houston', 'Dallas', 'San Antonio', 'Fort Worth', 'El Paso', 'Arlington'],
    'Washington': ['Seattle', 'Bellevue', 'Redmond', 'Tacoma', 'Spokane'],
    'Illinois': ['Chicago', 'Naperville', 'Aurora', 'Rockford'],
    'Massachusetts': ['Boston', 'Cambridge', 'Worcester', 'Springfield'],
    'Florida': ['Miami', 'Orlando', 'Tampa', 'Jacksonville', 'Fort Lauderdale'],
    'Georgia': ['Atlanta', 'Savannah', 'Augusta'],
    'Colorado': ['Denver', 'Boulder', 'Colorado Springs'],
  },
  'United Kingdom': {
    'England': ['London', 'Manchester', 'Birmingham', 'Leeds', 'Bristol', 'Cambridge', 'Oxford', 'Liverpool', 'Newcastle'],
    'Scotland': ['Edinburgh', 'Glasgow', 'Aberdeen', 'Dundee'],
    'Wales': ['Cardiff', 'Swansea', 'Newport'],
    'Northern Ireland': ['Belfast', 'Derry'],
  },
  'Germany': {
    'Berlin': ['Berlin'],
    'Bavaria': ['Munich', 'Nuremberg', 'Augsburg'],
    'Hesse': ['Frankfurt', 'Wiesbaden', 'Kassel'],
    'North Rhine-Westphalia': ['Cologne', 'Dusseldorf', 'Dortmund', 'Essen', 'Bonn'],
    'Hamburg': ['Hamburg'],
    'Baden-Wurttemberg': ['Stuttgart', 'Karlsruhe', 'Heidelberg'],
  },
  'Canada': {
    'Ontario': ['Toronto', 'Ottawa', 'Mississauga', 'Waterloo', 'Hamilton'],
    'British Columbia': ['Vancouver', 'Victoria', 'Burnaby', 'Surrey'],
    'Quebec': ['Montreal', 'Quebec City', 'Laval'],
    'Alberta': ['Calgary', 'Edmonton'],
  },
  'Singapore': {
    'Singapore': ['Singapore', 'Marina Bay', 'Changi', 'Jurong', 'Sentosa'],
  },
  'Australia': {
    'New South Wales': ['Sydney', 'Newcastle', 'Wollongong'],
    'Victoria': ['Melbourne', 'Geelong', 'Ballarat'],
    'Queensland': ['Brisbane', 'Gold Coast', 'Cairns'],
    'Western Australia': ['Perth', 'Fremantle'],
  },
  'Japan': {
    'Tokyo': ['Tokyo', 'Shibuya', 'Shinjuku', 'Minato', 'Chiyoda'],
    'Osaka': ['Osaka'],
    'Kyoto': ['Kyoto'],
    'Kanagawa': ['Yokohama'],
  },
  'France': {
    'Île-de-France': ['Paris', 'Boulogne-Billancourt', 'Saint-Denis'],
    'Auvergne-Rhône-Alpes': ['Lyon', 'Grenoble', 'Saint-Étienne'],
    'Provence-Alpes-Côte d\'Azur': ['Marseille', 'Nice', 'Cannes', 'Aix-en-Provence'],
    'Occitanie': ['Toulouse', 'Montpellier'],
    'Nouvelle-Aquitaine': ['Bordeaux', 'Limoges'],
  },
  'Italy': {
    'Lombardy': ['Milan', 'Bergamo', 'Brescia', 'Monza'],
    'Lazio': ['Rome'],
    'Piedmont': ['Turin'],
    'Veneto': ['Venice', 'Verona', 'Padua'],
    'Tuscany': ['Florence', 'Pisa'],
    'Emilia-Romagna': ['Bologna', 'Parma', 'Modena'],
  },
  'Spain': {
    'Community of Madrid': ['Madrid'],
    'Catalonia': ['Barcelona', 'Girona', 'Tarragona'],
    'Andalusia': ['Seville', 'Málaga', 'Granada', 'Córdoba'],
    'Valencian Community': ['Valencia', 'Alicante'],
    'Basque Country': ['Bilbao', 'San Sebastián'],
  },
  'Netherlands': {
    'North Holland': ['Amsterdam', 'Haarlem'],
    'South Holland': ['Rotterdam', 'The Hague', 'Leiden'],
    'Utrecht': ['Utrecht'],
    'North Brabant': ['Eindhoven', 'Tilburg', 'Breda'],
  },
  'Switzerland': {
    'Zurich': ['Zurich', 'Winterthur'],
    'Geneva': ['Geneva'],
    'Vaud': ['Lausanne'],
    'Basel-City': ['Basel'],
    'Bern': ['Bern'],
  },
  'Brazil': {
    'São Paulo': ['São Paulo', 'Campinas', 'Santos', 'Ribeirão Preto'],
    'Rio de Janeiro': ['Rio de Janeiro', 'Niterói'],
    'Minas Gerais': ['Belo Horizonte'],
    'Federal District': ['Brasília'],
    'Paraná': ['Curitiba'],
    'Rio Grande do Sul': ['Porto Alegre'],
  },
  'Mexico': {
    'Mexico City': ['Mexico City'],
    'Jalisco': ['Guadalajara', 'Zapopan', 'Puerto Vallarta'],
    'Nuevo León': ['Monterrey', 'San Pedro Garza García'],
    'Puebla': ['Puebla'],
    'Quintana Roo': ['Cancún', 'Playa del Carmen'],
  },
  'China': {
    'Beijing': ['Beijing'],
    'Shanghai': ['Shanghai'],
    'Guangdong': ['Guangzhou', 'Shenzhen', 'Dongguan', 'Foshan'],
    'Zhejiang': ['Hangzhou', 'Ningbo'],
    'Jiangsu': ['Nanjing', 'Suzhou'],
    'Sichuan': ['Chengdu'],
  },
  'South Africa': {
    'Gauteng': ['Johannesburg', 'Pretoria', 'Sandton'],
    'Western Cape': ['Cape Town', 'Stellenbosch'],
    'KwaZulu-Natal': ['Durban'],
  },
  'Saudi Arabia': {
    'Riyadh': ['Riyadh'],
    'Makkah': ['Jeddah', 'Mecca'],
    'Eastern Province': ['Dammam', 'Al Khobar', 'Dhahran'],
  },
};

/**
 * Returns list of states for a given country from standard reference
 */
export function getReferenceStatesForCountry(countryName: string): string[] {
  if (!countryName) return [];
  const cNorm = countryName.trim().toLowerCase();
  for (const [c, states] of Object.entries(COUNTRY_HIERARCHY)) {
    if (c.toLowerCase() === cNorm) {
      return Object.keys(states).sort();
    }
  }
  if (cNorm === 'uae' || cNorm === 'united arab emirates') {
    return Object.keys(COUNTRY_HIERARCHY['United Arab Emirates'] || {}).sort();
  }
  return [];
}

/**
 * Returns list of cities for a given country and state from standard reference
 */
export function getReferenceCitiesForState(countryName: string, stateName: string): string[] {
  if (!countryName || !stateName) return [];
  const cNorm = countryName.trim().toLowerCase();
  const sNorm = stateName.trim().toLowerCase();

  for (const [c, states] of Object.entries(COUNTRY_HIERARCHY)) {
    if (c.toLowerCase() === cNorm) {
      for (const [s, cities] of Object.entries(states)) {
        if (s.toLowerCase() === sNorm) {
          return cities.slice().sort();
        }
      }
    }
  }
  return [];
}

/**
 * Returns all cities for a country across all its states
 */
export function getReferenceCitiesForCountry(countryName: string): string[] {
  if (!countryName) return [];
  const cNorm = countryName.trim().toLowerCase();
  for (const [c, states] of Object.entries(COUNTRY_HIERARCHY)) {
    if (c.toLowerCase() === cNorm) {
      const allCities = Object.values(states).flat();
      return Array.from(new Set(allCities)).sort();
    }
  }
  return [];
}

/**
 * Returns states for multiple countries, tagging each state with its country
 */
export function getReferenceStatesForCountries(countryNames: string[]): Array<{ state: string; country: string }> {
  if (!countryNames || countryNames.length === 0) return [];
  const results: Array<{ state: string; country: string }> = [];
  const targetCountries = countryNames.map((c) => c.trim().toLowerCase());

  for (const [c, states] of Object.entries(COUNTRY_HIERARCHY)) {
    if (targetCountries.includes(c.toLowerCase()) || 
       (targetCountries.includes('uae') && c === 'United Arab Emirates')) {
      for (const state of Object.keys(states)) {
        results.push({ state, country: c });
      }
    }
  }
  return results.sort((a, b) => a.state.localeCompare(b.state));
}

/**
 * Returns cities for multiple countries and optionally filtered states
 */
export function getReferenceCitiesForCountriesAndStates(
  countryNames: string[],
  stateNames: string[]
): Array<{ city: string; state: string; country: string }> {
  if (!countryNames || countryNames.length === 0) return [];
  const results: Array<{ city: string; state: string; country: string }> = [];
  const targetCountries = countryNames.map((c) => c.trim().toLowerCase());
  const targetStates = stateNames.map((s) => s.trim().toLowerCase());

  for (const [c, states] of Object.entries(COUNTRY_HIERARCHY)) {
    if (targetCountries.includes(c.toLowerCase()) || 
       (targetCountries.includes('uae') && c === 'United Arab Emirates')) {
      for (const [state, cities] of Object.entries(states)) {
        if (targetStates.length === 0 || targetStates.includes(state.toLowerCase())) {
          for (const city of cities) {
            results.push({ city, state, country: c });
          }
        }
      }
    }
  }
  return results.sort((a, b) => a.city.localeCompare(b.city));
}

export interface DiscoveryLocation {
  country?: string;
  state?: string;
  city?: string;
}

/**
 * Turns the flat country / state / city selections into structured
 * locations so the backend knows which country every selected city and
 * state belongs to (otherwise "Hyderabad" or "Bavaria" is ambiguous, and
 * multi-country runs searched only the first country).
 */
export function buildDiscoveryLocations(countries: string[], states: string[], cities: string[]): DiscoveryLocation[] {
  const out: DiscoveryLocation[] = [];
  const usedCities = new Set<string>();
  const usedStates = new Set<string>();
  const citySet = new Set(cities);
  const stateSet = new Set(states);
  for (const country of countries) {
    const tree = COUNTRY_HIERARCHY[country] || {};
    let added = false;
    for (const [state, stateCities] of Object.entries(tree)) {
      const picked = stateCities.filter((c) => citySet.has(c) && !usedCities.has(c));
      if (picked.length) {
        for (const city of picked) {
          out.push({ country, state, city });
          usedCities.add(city);
        }
        usedStates.add(state);
        added = true;
      } else if (stateSet.has(state) && !usedStates.has(state)) {
        out.push({ country, state });
        usedStates.add(state);
        added = true;
      }
    }
    if (!added) out.push({ country });
  }
  // Selections outside the reference hierarchy are still sent; the backend infers their country.
  for (const city of cities) if (!usedCities.has(city)) out.push({ city });
  for (const state of states) if (!usedStates.has(state)) out.push({ state });
  return out;
}

/**
 * The picker's state -> cities lists for every country where a whole state
 * is ticked (a state with none of its cities ticked). The backend uses them
 * to tell which state an event's city is in, so "Bavaria" keeps Munich and
 * Nuremberg events and rejects Berlin ones.
 */
export function buildRegionCities(countries: string[], states: string[], cities: string[]): Record<string, Record<string, string[]>> {
  const out: Record<string, Record<string, string[]>> = {};
  const citySet = new Set(cities);
  const stateSet = new Set(states);
  for (const country of countries) {
    const tree = COUNTRY_HIERARCHY[country];
    if (!tree) continue;
    const hasWholeState = Object.entries(tree).some(([state, stateCities]) => stateSet.has(state) && !stateCities.some((c) => citySet.has(c)));
    if (hasWholeState) out[country] = tree;
  }
  return out;
}
