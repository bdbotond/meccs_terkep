#!/usr/bin/env python3
"""
MLSZ Match Scraper
Fetches adult league matches (NB I, NB II, NB III, Megye I-IV) from adatbank.mlsz.hu
and outputs normalized JSON files with geocoded venues.
Supports incremental upsert: modifies or extends database, replacing changed values.
"""

import os
import sys
import re
import json
import time
import argparse
import urllib.request
import urllib.parse
import urllib.error
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

BASE_API_URL = "https://ada1bank.mlsz.hu/libs/ajax.php"
BASE_SITE_URL = "https://adatbank.mlsz.hu/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
VENUES_FILE = os.path.join(DATA_DIR, "venues.json")
LEAGUES_FILE = os.path.join(DATA_DIR, "leagues.json")
MATCHES_FILE = os.path.join(DATA_DIR, "matches.json")
DATASET_JS_FILE = os.path.join(DATA_DIR, "dataset.js")

# Regional center coordinates fallback for Hungarian counties / regions
REGION_FALLBACK_COORDS = {
    "MLSZ": (47.1625, 19.5033),
    "Budapest": (47.4979, 19.0402),
    "Bács-Kiskun": (46.9074, 19.6917),
    "Baranya": (46.0727, 18.2323),
    "Békés": (46.6793, 21.0911),
    "Borsod-Abaúj-Zemplén": (48.1035, 20.7784),
    "Csongrád": (46.2530, 20.1414),
    "Csongrád-Csanád": (46.2530, 20.1414),
    "Fejér": (47.1860, 18.4221),
    "Győr-Moson-Sopron": (47.6875, 17.6504),
    "Hajdú-Bihar": (47.5316, 21.6273),
    "Heves": (47.9025, 20.3772),
    "Jász-Nagykun-Szolnok": (47.1747, 20.1983),
    "Komárom-Esztergom": (47.5692, 18.3970),
    "Nógrád": (48.0988, 19.8030),
    "Pest": (47.5300, 19.3000),
    "Somogy": (46.3593, 17.7967),
    "Szabolcs-Szatmár-Bereg": (47.9554, 21.7167),
    "Tolna": (46.3501, 18.7090),
    "Vas": (47.2307, 16.6218),
    "Veszprém": (47.0933, 17.9115),
    "Zala": (46.8417, 16.8439)
}

BAD_ZALAAPATI_LAT = 46.73898
BAD_ZALAAPATI_LNG = 17.11004

NON_TOWN_PREFIXES = {
    'város', 'központ', 'megye', 'egyetem', 'főváros', 'nemzeti',
    'szabadidő', 'iskola', 'vasutas', 'bányász', 'honvéd', 'rendőrségi',
    'művelődési', 'sport', 'foci'
}


def is_in_hungary(lat, lng):
    """Validate coordinates within Hungarian geographic bounding box."""
    return 45.7 <= lat <= 48.65 and 16.1 <= lng <= 22.9


def make_request(url, data=None, headers=None, timeout=15, max_retries=2):
    hdrs = {'User-Agent': USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs)
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries:
                time.sleep(1.0)
                continue
            raise e


def post_mlsz_api(payload):
    data = urllib.parse.urlencode(payload).encode('utf-8')
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://ada1bank.mlsz.hu/league'
    }
    raw = make_request(BASE_API_URL, data=data, headers=headers)
    return json.loads(raw.decode('utf-8'))


def detect_season():
    try:
        html = make_request(BASE_SITE_URL).decode('utf-8')
        m = re.search(r'season\s*:\s*(\d+)', html)
        if m:
            return m.group(1)
        m = re.search(r'/league/(\d+)/', html)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"Warning: could not detect season dynamically ({e}), falling back to 67", file=sys.stderr)
    return "67"


def classify_league(name, federation_name):
    """
    Classify adult Hungarian field football leagues into:
    NB I, NB II, NB III, Megye I, Megye II, Megye III, Megye IV
    Filters out all youth, veteran, futsal, women, reserves, and cup competitions.
    """
    upper = name.upper()

    # Reject youth, veteran, futsal, women, cup, tournaments, reserves
    youth_or_non_adult_regex = (
        r'U[-_\s]?\d+|OLD\s*BOY|ÖREGFIÚ|VETERÁN|LEÁNY|NŐI|FUTSAL|'
        r'KUPA|SZUPERKUPA|TÉLI|STRAND|KISPÁLYÁ|TORNA|EDZŐMÉRKŐZÉS|'
        r'UTÁNPÓTLÁS|IFJÚSÁGI|IFI|SERDÜLŐ|KÖLYÖK|TARTALÉK'
    )
    if re.search(youth_or_non_adult_regex, upper):
        return None

    # National leagues (MLSZ)
    if federation_name == "MLSZ":
        if re.search(r'OTP\s*BANK|NB\s*I', upper):
            return "NB I"
        if re.search(r'MERKANTIL|NB\s*II', upper):
            return "NB II"
        if "NB III" in upper:
            return "NB III"
        return None

    # County leagues (BLSZ / Vármegye / Megye I-IV)
    # Check Megye IV first down to Megye I to avoid prefix false positives
    if re.search(r'BLSZ\s*IV|(?:VÁR)?MEGYE(?:I)?\s*IV|IV\.?\s*(?:OSZTÁLY|O|O\.)', upper):
        return "Megye IV"
    if re.search(r'BLSZ\s*III|(?:VÁR)?MEGYE(?:I)?\s*III|III\.?\s*(?:OSZTÁLY|O|O\.)', upper):
        return "Megye III"
    if re.search(r'BLSZ\s*II|(?:VÁR)?MEGYE(?:I)?\s*II|II\.?\s*(?:OSZTÁLY|O|O\.)', upper):
        return "Megye II"
    if re.search(r'BLSZ\s*I|(?:VÁR)?MEGYE(?:I)?\s*I|I\.?\s*(?:OSZTÁLY|O|O\.)', upper):
        return "Megye I"

    return None


def extract_town_from_arena(arena_name, home_team=""):
    cleaned = arena_name.strip()
    if not cleaned:
        return ""

    # Known Hungarian arenas with fixed settlements
    if "Pancho" in cleaned:
        return "Felcsút"
    if any(k in cleaned for k in ["Bozsik", "Hidegkuti", "Illovszky", "Szusza", "Groupama", "Szabadkikötő"]):
        return "Budapest"
    if "Nagyerdei" in cleaned:
        return "Debrecen"

    # Match 'Alsópáhoki Sportpálya', 'Kemendollári Sporttelep', etc.
    m = re.match(r'^([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüűA-ZÁÉÍÓÖŐÚÜŰ\-]+?)(?:i|ei|ai)?\s+(?:Sportpálya|Sporttelep|Sportcentrum|Labdarúgó|Városi|Stadion|SE|FC|KSE|SK)', cleaned, re.I)
    if m:
        base = m.group(1)
        if base.lower() not in NON_TOWN_PREFIXES:
            if base.endswith('y') and cleaned.startswith(base + 'ei'):
                return base + 'e'
            if cleaned.startswith(base + 'ai') and not base.endswith('a'):
                return base + 'a'
            return base

    # Match from home team name if available (e.g. 'Kemendollári LSC' -> Kemendollár, 'Bak SE' -> Bak)
    if home_team:
        m2 = re.match(r'^([A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüűA-ZÁÉÍÓÖŐÚÜŰ\-]+?)(?:i|ei|ai)?\s+(?:SE|FC|TE|SC|KSE|LSC|TC|VSC|SK|VSE|BSE|DSE|KFC|MSE|KLE|LE|USE|CS|AC)', home_team.strip(), re.I)
        if m2:
            base2 = m2.group(1)
            if base2.lower() not in NON_TOWN_PREFIXES:
                if base2.endswith('y') and home_team.startswith(base2 + 'ei'):
                    return base2 + 'e'
                if home_team.startswith(base2 + 'ai') and not base2.endswith('a'):
                    return base2 + 'a'
                return base2

    # First word with adjective stripping
    first_word = cleaned.split()[0]
    if first_word.lower() not in NON_TOWN_PREFIXES:
        if first_word.endswith('i') and len(first_word) > 3:
            stem = first_word[:-1]
            if stem.endswith('á'):
                stem = stem[:-1] + 'a'
            elif stem.endswith('é'):
                stem = stem[:-1] + 'e'
            elif first_word.endswith('ai'):
                stem += 'a'
            if stem.lower() not in NON_TOWN_PREFIXES:
                return stem
        return first_word

    if home_team:
        ht_first = home_team.strip().split()[0]
        if ht_first.lower() not in NON_TOWN_PREFIXES:
            return ht_first

    return ""


class Geocoder:
    def __init__(self, venues_path):
        self.venues_path = venues_path
        self.venues = {}
        if os.path.exists(venues_path):
            try:
                with open(venues_path, "r", encoding="utf-8") as f:
                    self.venues = json.load(f)
            except Exception:
                self.venues = {}

    def save(self):
        os.makedirs(os.path.dirname(self.venues_path), exist_ok=True)
        with open(self.venues_path, "w", encoding="utf-8") as f:
            json.dump(self.venues, f, ensure_ascii=False, indent=2)

    def is_bad_venue(self, venue_info):
        if not venue_info:
            return True
        lat = venue_info.get("lat", 0)
        lng = venue_info.get("lng", 0)
        if not is_in_hungary(lat, lng):
            return True
        if abs(lat - BAD_ZALAAPATI_LAT) < 0.001 and abs(lng - BAD_ZALAAPATI_LNG) < 0.001:
            return True
        return False

    def geocode(self, arena_name, region_name="", home_team=""):
        cleaned = arena_name.strip()
        if not cleaned:
            return None

        # Check existing cache (if valid and within Hungary)
        if cleaned in self.venues and not self.is_bad_venue(self.venues[cleaned]):
            return self.venues[cleaned]

        # Specific alias overrides for tricky arenas
        if "Pancho" in cleaned:
            venue_info = {
                "name": cleaned,
                "lat": 47.46396,
                "lng": 18.58662,
                "address": "Pancho Aréna, Felcsút"
            }
            self.venues[cleaned] = venue_info
            return venue_info

        if "MITE" in cleaned:
            venue_info = {
                "name": cleaned,
                "lat": 47.4735,
                "lng": 19.0558,
                "address": "MITE Sporttelep, Budapest"
            }
            self.venues[cleaned] = venue_info
            return venue_info

        if "Biri" in cleaned:
            venue_info = {
                "name": cleaned,
                "lat": 47.8123,
                "lng": 21.85095,
                "address": "Biri SE Sporttelep, Biri"
            }
            self.venues[cleaned] = venue_info
            return venue_info

        reg_clean = "" if region_name in ["MLSZ", "0", ""] else region_name
        town = extract_town_from_arena(cleaned, home_team)

        # Build candidate search queries in priority order
        queries = []
        if cleaned and reg_clean:
            queries.append(f"{cleaned} {reg_clean} Hungary")
        if cleaned:
            queries.append(f"{cleaned} Hungary")
        if town and reg_clean:
            queries.append(f"{town} {reg_clean} Hungary")
        if town:
            queries.append(f"{town} Hungary")
        if reg_clean:
            queries.append(f"{reg_clean} Hungary")

        coords = None
        display_name = ""

        generic_names = {'sportpálya utca', 'sportpálya', 'temető', 'focipálya', 'sporttelep'}

        for q in queries:
            try:
                url = f"https://photon.komoot.io/api/?q={urllib.parse.quote(q)}&limit=1"
                raw = make_request(url, timeout=8)
                data = json.loads(raw.decode("utf-8"))
                features = data.get("features", [])
                if features:
                    feat = features[0]
                    props = feat.get("properties", {})
                    feat_name = (props.get("name") or "").strip().lower()

                    # Avoid generic "Sportpálya utca" unless query specifically requested it
                    if feat_name in generic_names and town and town.lower() not in feat_name:
                        continue

                    # Validate country code is Hungary if available
                    cc = props.get("countrycode", "").upper()
                    if cc and cc != "HU":
                        continue

                    lon, lat = feat["geometry"]["coordinates"]
                    # Validate coordinate bounds
                    if not is_in_hungary(lat, lon):
                        continue

                    display_name = props.get("name") or props.get("city") or cleaned
                    coords = (round(lat, 5), round(lon, 5))
                    break
            except Exception:
                pass
            time.sleep(0.3)

        if not coords or (abs(coords[0] - BAD_ZALAAPATI_LAT) < 0.001 and abs(coords[1] - BAD_ZALAAPATI_LNG) < 0.001) or not is_in_hungary(coords[0], coords[1]):
            if region_name in REGION_FALLBACK_COORDS:
                coords = REGION_FALLBACK_COORDS[region_name]
                display_name = f"{cleaned} ({region_name})"
            else:
                coords = (47.1625, 19.5033)
                display_name = cleaned

        venue_info = {
            "name": cleaned,
            "lat": coords[0],
            "lng": coords[1],
            "address": display_name
        }
        self.venues[cleaned] = venue_info
        return venue_info


def parse_round_matches(season, fed_id, league_id, turn_number):
    if BeautifulSoup is None:
        raise RuntimeError("BeautifulSoup4 is required for parsing HTML matches. Install with: pip install beautifulsoup4")
    url = f"{BASE_SITE_URL}league/{season}/{fed_id}/{league_id}/{turn_number}.html"
    try:
        html = make_request(url, timeout=12).decode('utf-8')
    except Exception as e:
        print(f"  Error fetching round {turn_number}: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, 'html.parser')
    panel = soup.find('div', class_='sorsolas_panel')
    if not panel:
        panel = soup

    matches = []
    for box in panel.find_all('div', class_='schedule'):
        home_el = box.find('div', class_='home_team')
        away_el = box.find('div', class_='away_team')
        date_el = box.find('div', class_='team_sorsolas_date')
        arena_el = box.find('div', class_='team_sorsolas_arena')
        res_el = box.find('div', class_='result')

        home_team = home_el.get_text(strip=True) if home_el else ''
        away_team = away_el.get_text(strip=True) if away_el else ''
        arena = arena_el.get_text(strip=True) if arena_el else ''
        dt_raw = date_el.get_text(' ', strip=True) if date_el else ''
        res_raw = res_el.get_text(strip=True) if res_el else ''

        if not home_team or not away_team:
            continue

        # Extract MLSZ match ID
        match_id = ""
        link = box.find('a', href=re.compile(r'/match/'))
        if link:
            m = re.search(r'/match/(?:[^/]+/)*(\d+)\.html', link['href'])
            if m:
                match_id = m.group(1)

        # Parse date and time
        date_str = ""
        time_str = ""
        m_dt = re.search(r'(\d{4})[.\s-]+(\d{1,2})[.\s-]+(\d{1,2})', dt_raw)
        if m_dt:
            y, mth, d = m_dt.groups()
            date_str = f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"

        m_time = re.search(r'(\d{1,2}):(\d{2})', dt_raw)
        if m_time:
            hr, mn = m_time.groups()
            time_str = f"{int(hr):02d}:{int(mn):02d}"

        # Clean score - match final scores and administrative results (e.g. "3 - 1", "0 - 0", "3 - 0 vb")
        score = ""
        clean_res = res_raw.replace('–', '-').strip()
        m_score = re.match(r'^\s*(\d{1,2})\s*-\s*(\d{1,2})(?:\s*(?:vb|h\.u\.|bün\.|félbeszakadt))?\s*$', clean_res, re.I)
        if m_score:
            extra = " vb" if "vb" in clean_res.lower() else ""
            score = f"{m_score.group(1)} - {m_score.group(2)}{extra}"

        matches.append({
            "id": match_id or f"{league_id}_{turn_number}_{len(matches)+1}",
            "lid": str(league_id),
            "vid": arena,
            "d": date_str,
            "t": time_str,
            "h": home_team,
            "a": away_team,
            "s": score,
            "round": str(turn_number)
        })

    return matches


def prune_database(leagues_data, all_matches_list):
    """Purge youth, veteran, and non-adult leagues and matches."""
    valid_leagues = {}
    removed_leagues = set()
    for lid, l in list(leagues_data.items()):
        lvl = classify_league(l.get('name', ''), l.get('federation', ''))
        if lvl:
            l['level'] = lvl
            valid_leagues[str(lid)] = l
        else:
            removed_leagues.add(str(lid))

    valid_matches = [m for m in all_matches_list if str(m.get('lid', '')) in valid_leagues]
    pruned_matches_count = len(all_matches_list) - len(valid_matches)

    if removed_leagues or pruned_matches_count:
        print(f"Database cleanup: removed {len(removed_leagues)} non-adult leagues and {pruned_matches_count} matches.")

    return valid_leagues, valid_matches


def scrape(args):
    os.makedirs(DATA_DIR, exist_ok=True)
    geocoder = Geocoder(VENUES_FILE)

    season = args.season or detect_season()
    print(f"Season detected: {season}")

    # Load existing database to extend or modify in-place
    leagues_data = {}
    if os.path.exists(LEAGUES_FILE):
        try:
            with open(LEAGUES_FILE, "r", encoding="utf-8") as f:
                leagues_data = json.load(f)
        except Exception:
            leagues_data = {}

    all_matches = []
    if os.path.exists(MATCHES_FILE) and not args.fresh:
        try:
            with open(MATCHES_FILE, "r", encoding="utf-8") as f:
                all_matches = json.load(f)
        except Exception:
            all_matches = []

    # Clean existing database of non-adult entries if present
    leagues_data, all_matches = prune_database(leagues_data, all_matches)

    # Build existing lookups: by ID and by fixture tuple including round
    match_dict = {}
    fixture_dict = {}

    for m in all_matches:
        mid = str(m.get("id", ""))
        if not mid:
            mid = f"{m.get('lid')}_{m.get('round', '0')}_{len(match_dict)+1}"
            m["id"] = mid
        match_dict[mid] = m
        # Key by (league_id, round, home_team, away_team)
        fix_key = (str(m.get("lid", "")), str(m.get("round", "")), m.get("h", "").strip(), m.get("a", "").strip())
        fixture_dict[fix_key] = m

    target_leagues = []

    # Fetch initial federation list
    print("Discovering federations and leagues...")
    try:
        init_data = post_mlsz_api({
            'type': 'getHeaderFilderData',
            'season': season,
            'federationId': '0',
            'leagueId': '-1',
            'changedType': 'first'
        })
        federations = init_data.get('federations', [])
        print(f"Found {len(federations)} federations.")
    except Exception as e:
        print(f"Error connecting to MLSZ API ({e})", file=sys.stderr)
        return

    if args.test_league:
        test_lid = str(args.test_league)
        found_league = None

        # Try to locate the league dynamically among federations
        for fed in federations:
            fed_id = str(fed['id'])
            fed_name = fed['name']
            if args.fed and str(args.fed) != fed_id and str(args.fed).lower() != fed_name.lower():
                continue
            try:
                fed_data = post_mlsz_api({
                    'type': 'getHeaderFilderData',
                    'season': season,
                    'federationId': fed_id,
                    'leagueId': '-1',
                    'changedType': 'federation'
                })
                for l in fed_data.get('leagues', []):
                    if str(l['id']) == test_lid:
                        lvl = classify_league(l['name'], fed_name) or "NB I"
                        found_league = {
                            "id": test_lid,
                            "name": l['name'].strip(),
                            "level": lvl,
                            "federation": fed_name,
                            "fed_id": fed_id
                        }
                        break
            except Exception:
                pass
            if found_league:
                break

        if not found_league:
            found_league = {
                "id": test_lid,
                "name": "OTP Bank Liga",
                "level": "NB I",
                "federation": "MLSZ",
                "fed_id": "0"
            }
        target_leagues.append(found_league)
        print(f"Targeting single league: {found_league['name']} ({found_league['federation']} - {found_league['level']})")
    else:
        for fed in federations:
            fed_id = str(fed['id'])
            fed_name = fed['name']

            # Optional federation filter
            if args.fed and str(args.fed) != fed_id and str(args.fed).lower() != fed_name.lower():
                continue

            try:
                fed_data = post_mlsz_api({
                    'type': 'getHeaderFilderData',
                    'season': season,
                    'federationId': fed_id,
                    'leagueId': '-1',
                    'changedType': 'federation'
                })
                leagues = fed_data.get('leagues', [])
                for l in leagues:
                    lvl = classify_league(l['name'], fed_name)
                    if lvl:
                        if args.level and lvl.lower() != args.level.lower():
                            continue
                        target_leagues.append({
                            "id": str(l['id']),
                            "name": l['name'].strip(),
                            "level": lvl,
                            "federation": fed_name,
                            "fed_id": fed_id
                        })
            except Exception as e:
                print(f"Failed to fetch leagues for federation {fed_name}: {e}", file=sys.stderr)

        print(f"Identified {len(target_leagues)} adult leagues across Hungary matching criteria.")

        if args.limit_leagues:
            target_leagues = target_leagues[:args.limit_leagues]
            print(f"Limited to first {len(target_leagues)} leagues.")

    # Tracking counters
    new_matches_count = 0
    updated_matches_count = 0
    unchanged_matches_count = 0

    # Process target leagues
    for idx, l in enumerate(target_leagues, 1):
        lid = l['id']
        lname = l['name']
        fed_id = l['fed_id']
        fed_name = l['federation']
        level = l['level']

        print(f"[{idx}/{len(target_leagues)}] Scraping {lname} ({fed_name} - {level})...")

        # Upsert league
        leagues_data[lid] = {
            "id": lid,
            "name": lname,
            "level": level,
            "federation": fed_name
        }

        # Fetch turns
        try:
            turns_data = post_mlsz_api({
                'type': 'getHeaderFilderData',
                'season': season,
                'federationId': fed_id,
                'leagueId': lid,
                'changedType': 'league'
            })
            turns = turns_data.get('turns', [])
        except Exception as e:
            print(f"  Error fetching turns for league {lid}: {e}", file=sys.stderr)
            continue

        if not turns:
            turns = [{'turn': str(i)} for i in range(1, 31)]

        for t in turns:
            turn_no = t.get('turn')
            matches = parse_round_matches(season, fed_id, lid, turn_no)
            for m in matches:
                # Geocode arena if not yet cached or if cached bad
                arena = m['vid']
                if arena and not args.skip_geocoding:
                    geocoder.geocode(arena, fed_name, m['h'])

                # Upsert match into database
                mid = str(m['id'])
                fix_key = (str(m['lid']), str(m.get('round', '')), m['h'].strip(), m['a'].strip())

                existing = match_dict.get(mid) or fixture_dict.get(fix_key)

                if existing:
                    old_id = str(existing.get('id', ''))
                    changed = False
                    for prop in ['d', 't', 'vid', 's', 'id', 'round']:
                        new_val = m.get(prop)
                        if new_val is not None and new_val != existing.get(prop):
                            existing[prop] = new_val
                            changed = True

                    # Re-sync match_dict if ID changed (e.g. synthetic ID -> real MLSZ ID)
                    new_id = str(existing.get('id', ''))
                    if old_id != new_id:
                        match_dict.pop(old_id, None)
                        match_dict[new_id] = existing

                    if changed:
                        updated_matches_count += 1
                    else:
                        unchanged_matches_count += 1
                else:
                    match_dict[mid] = m
                    fixture_dict[fix_key] = m
                    new_matches_count += 1

            time.sleep(0.1)

        # Save venues incrementally
        geocoder.save()

    # Final prune check to guarantee data cleanliness
    leagues_data, all_matches_list = prune_database(leagues_data, list(match_dict.values()))

    # Sort matches chronologically
    all_matches_list.sort(key=lambda x: (x.get("d") or "9999", x.get("t") or "99:99"))

    # Final persist of all datasets
    geocoder.save()

    with open(LEAGUES_FILE, "w", encoding="utf-8") as f:
        json.dump(leagues_data, f, ensure_ascii=False, indent=2)

    with open(MATCHES_FILE, "w", encoding="utf-8") as f:
        json.dump(all_matches_list, f, ensure_ascii=False)

    with open(DATASET_JS_FILE, "w", encoding="utf-8") as f:
        f.write("window.MECCS_DATA = " + json.dumps({
            "leagues": leagues_data,
            "venues": geocoder.venues,
            "matches": all_matches_list
        }, ensure_ascii=False) + ";\n")

    print(f"\nDone! Database summary:")
    print(f"  - New matches added: {new_matches_count}")
    print(f"  - Existing matches updated: {updated_matches_count}")
    print(f"  - Unchanged matches: {unchanged_matches_count}")
    print(f"  - Total matches in database: {len(all_matches_list)}")
    print(f"  - Total leagues in database: {len(leagues_data)}")
    print(f"  - Total venues in database: {len(geocoder.venues)}")


def fix_clustered_venues(venues_file):
    if not os.path.exists(venues_file):
        return
    with open(venues_file, "r", encoding="utf-8") as f:
        venues = json.load(f)

    from collections import Counter
    coord_counts = Counter((round(v.get('lat', 0), 4), round(v.get('lng', 0), 4)) for v in venues.values())
    clustered_coords = {coord for coord, count in coord_counts.items() if count >= 3}

    fixed = 0
    total_to_check = sum(1 for v in venues.values() if (round(v.get('lat', 0), 4), round(v.get('lng', 0), 4)) in clustered_coords or (abs(v.get('lat', 0) - BAD_ZALAAPATI_LAT) < 0.001 and abs(v.get('lng', 0) - BAD_ZALAAPATI_LNG) < 0.001) or not is_in_hungary(v.get('lat', 0), v.get('lng', 0)))
    print(f"Checking {total_to_check} clustered or invalid venues for real town coordinates...")

    for name, info in list(venues.items()):
        coord = (round(info.get('lat', 0), 4), round(info.get('lng', 0), 4))
        is_bad = (coord in clustered_coords) or (abs(info.get('lat', 0) - BAD_ZALAAPATI_LAT) < 0.001 and abs(info.get('lng', 0) - BAD_ZALAAPATI_LNG) < 0.001) or (not is_in_hungary(info.get('lat', 0), info.get('lng', 0)))

        if is_bad:
            town = extract_town_from_arena(name)
            if town and len(town) >= 3 and town.lower() not in NON_TOWN_PREFIXES:
                q = f"{town} Hungary"
                try:
                    url = f"https://photon.komoot.io/api/?q={urllib.parse.quote(q)}&limit=1"
                    raw = make_request(url, timeout=8)
                    data = json.loads(raw.decode("utf-8"))
                    features = data.get("features", [])
                    if features:
                        lon, lat = features[0]["geometry"]["coordinates"]
                        props = features[0].get("properties", {})
                        cc = props.get("countrycode", "").upper()
                        if cc and cc != "HU":
                            continue
                        if not is_in_hungary(lat, lon):
                            continue
                        disp = props.get("name") or town
                        new_lat = round(lat, 5)
                        new_lng = round(lon, 5)
                        # Check that it's not the same cluster
                        if (round(new_lat, 4), round(new_lng, 4)) != coord:
                            venues[name] = {
                                "name": name,
                                "lat": new_lat,
                                "lng": new_lng,
                                "address": f"{name} ({disp})"
                            }
                            fixed += 1
                except Exception:
                    pass
                time.sleep(0.2)

    with open(venues_file, "w", encoding="utf-8") as f:
        json.dump(venues, f, ensure_ascii=False, indent=2)

    # Also update dataset.js if matches exist
    if os.path.exists(MATCHES_FILE) and os.path.exists(LEAGUES_FILE):
        try:
            with open(LEAGUES_FILE, "r", encoding="utf-8") as lf, open(MATCHES_FILE, "r", encoding="utf-8") as mf:
                ld = json.load(lf)
                md = json.load(mf)
            with open(DATASET_JS_FILE, "w", encoding="utf-8") as df:
                df.write("window.MECCS_DATA = " + json.dumps({
                    "leagues": ld,
                    "venues": venues,
                    "matches": md
                }, ensure_ascii=False) + ";\n")
        except Exception as e:
            print(f"Warning: could not update dataset.js: {e}", file=sys.stderr)

    print(f"Successfully re-geocoded and fixed {fixed} venues to authentic town coordinates.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MLSZ Football Matches Scraper")
    parser.add_argument("--test-league", type=str, help="Scrape single league ID (e.g. 33586 for OTP Bank Liga)")
    parser.add_argument("--limit-leagues", type=int, help="Limit number of leagues to scrape")
    parser.add_argument("--level", type=str, help="Filter by level (e.g. 'NB I', 'NB II', 'NB III', 'Megye I')")
    parser.add_argument("--fed", type=str, help="Filter by federation ID or name")
    parser.add_argument("--season", type=str, help="Override season ID (default: 67)")
    parser.add_argument("--fresh", action="store_true", help="Discard existing matches and scrape fresh")
    parser.add_argument("--full", action="store_true", help="Perform full scrape of all adult leagues across Hungary")
    parser.add_argument("--skip-geocoding", action="store_true", help="Skip geocoding new venues")
    parser.add_argument("--fix-venues", action="store_true", help="Fix clustered venues using smart town geocoding")
    parser.add_argument("--prune", action="store_true", help="Clean database by purging youth and non-adult leagues/matches")
    args = parser.parse_args()

    if args.prune:
        if os.path.exists(LEAGUES_FILE) and os.path.exists(MATCHES_FILE):
            with open(LEAGUES_FILE, 'r', encoding='utf-8') as lf, open(MATCHES_FILE, 'r', encoding='utf-8') as mf:
                ld = json.load(lf)
                md = json.load(mf)
            ld_clean, md_clean = prune_database(ld, md)
            with open(LEAGUES_FILE, 'w', encoding='utf-8') as lf, open(MATCHES_FILE, 'w', encoding='utf-8') as mf:
                json.dump(ld_clean, lf, ensure_ascii=False, indent=2)
                json.dump(md_clean, mf, ensure_ascii=False)
            if os.path.exists(VENUES_FILE):
                with open(VENUES_FILE, 'r', encoding='utf-8') as vf:
                    vd = json.load(vf)
                with open(DATASET_JS_FILE, 'w', encoding='utf-8') as df:
                    df.write('window.MECCS_DATA = ' + json.dumps({
                        'leagues': ld_clean,
                        'venues': vd,
                        'matches': md_clean
                    }, ensure_ascii=False) + ';\n')
            print('Prune complete.')
    elif args.fix_venues:
        fix_clustered_venues(VENUES_FILE)
    else:
        scrape(args)
