#!/usr/bin/env python3
"""
MLSZ Match Scraper
Fetches adult league matches (NB I, NB II, NB III, Megye I-IV) from adatbank.mlsz.hu
and outputs normalized JSON files with geocoded venues.
"""

import os
import sys
import re
import json
import time
import argparse
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup

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
    "MLSZ": (47.4979, 19.0402),
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


def make_request(url, data=None, headers=None, timeout=15):
    hdrs = {'User-Agent': USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


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
    upper = name.upper()

    # Reject youth, veteran, futsal, women, cup
    negatives = [
        "U19", "U18", "U17", "U16", "U15", "U14", "U13", "U12", "U11", "U10", "U9", "U8", "U7",
        "ÖREGFIÚ", "VETERÁN", "FUTSAL", "NŐI", "KUPA", "TÉLI", "STRANDLABDARÚGÁS"
    ]
    if any(neg in upper for neg in negatives):
        return None

    # National leagues
    if federation_name == "MLSZ":
        if "OTP BANK" in upper or "NB I." in upper or upper == "NB I":
            return "NB I"
        if "MERKANTIL" in upper or "NB II." in upper or upper == "NB II":
            return "NB II"
        if "NB III" in upper:
            return "NB III"
        return None

    # County leagues (Megye / Vármegye / BLSZ)
    if any(k in upper for k in ["BLSZ I", "MEGYE I.", "MEGYEI I", "VÁRMEGYE I.", "VÁRMEGYEI I.", " I. OSZTÁLY"]):
        return "Megye I"
    if any(k in upper for k in ["BLSZ II", "MEGYE II.", "MEGYEI II", "VÁRMEGYE II.", "VÁRMEGYEI II.", " II. OSZTÁLY"]):
        return "Megye II"
    if any(k in upper for k in ["BLSZ III", "MEGYE III.", "MEGYEI III", "VÁRMEGYE III.", "VÁRMEGYEI III.", " III. OSZTÁLY"]):
        return "Megye III"
    if any(k in upper for k in ["BLSZ IV", "MEGYE IV.", "MEGYEI IV", "VÁRMEGYE IV.", "VÁRMEGYEI IV.", " IV. OSZTÁLY"]):
        return "Megye IV"

    return None


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

    def geocode(self, arena_name, region_name=""):
        cleaned = arena_name.strip()
        if not cleaned:
            return None

        if cleaned in self.venues:
            return self.venues[cleaned]

        # Specific alias overrides for tricky Hungarian arenas
        if "Pancho" in cleaned:
            venue_info = {
                "name": cleaned,
                "lat": 47.46396,
                "lng": 18.58662,
                "address": "Pancho Aréna, Felcsút"
            }
            self.venues[cleaned] = venue_info
            return venue_info

        reg_clean = "" if region_name in ["MLSZ", "0", ""] else region_name

        # Query candidates
        queries = [
            f"{cleaned} {reg_clean} Hungary".strip(),
            f"{cleaned} Hungary",
            f"{reg_clean} Hungary" if reg_clean else "Hungary"
        ]

        coords = None
        display_name = ""

        for q in queries:
            try:
                url = f"https://photon.komoot.io/api/?q={urllib.parse.quote(q)}&limit=1"
                raw = make_request(url, timeout=8)
                data = json.loads(raw.decode("utf-8"))
                features = data.get("features", [])
                if features:
                    lon, lat = features[0]["geometry"]["coordinates"]
                    props = features[0].get("properties", {})
                    display_name = props.get("name") or props.get("city") or cleaned
                    coords = (round(lat, 5), round(lon, 5))
                    break
            except Exception:
                pass
            time.sleep(0.3)

        if not coords:
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

        # Extract match ID
        match_id = ""
        link = box.find('a', href=re.compile(r'/match/'))
        if link:
            m = re.search(r'/match/(?:[^/]+/)*(\d+)\.html', link['href'])
            if m:
                match_id = m.group(1)

        # Parse date and time
        # Typical: "2026. 07. 26. 18:00" or "2027. 05. 22."
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

        # Clean score - only match actual final scores (e.g. "3 - 1", "0 - 0")
        score = ""
        clean_res = res_raw.replace('–', '-').strip()
        m_score = re.match(r'^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$', clean_res)
        if m_score:
            score = f"{m_score.group(1)} - {m_score.group(2)}"

        matches.append({
            "id": match_id or f"{league_id}_{turn_number}_{len(matches)+1}",
            "lid": str(league_id),
            "vid": arena,
            "d": date_str,
            "t": time_str,
            "h": home_team,
            "a": away_team,
            "s": score
        })

    return matches


def scrape(args):
    os.makedirs(DATA_DIR, exist_ok=True)
    geocoder = Geocoder(VENUES_FILE)

    season = args.season or detect_season()
    print(f"Season detected: {season}")

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

    # Map of match id to match dict for deduplication
    match_dict = {str(m["id"]): m for m in all_matches}

    target_leagues = []

    if args.test_league:
        # OTP Bank Liga or specified single league
        league_id = args.test_league
        target_leagues.append({
            "id": str(league_id),
            "name": "OTP Bank Liga",
            "level": "NB I",
            "federation": "MLSZ",
            "fed_id": "0"
        })
    else:
        # Discover adult leagues via MLSZ API
        print("Discovering federations and leagues...")
        init_data = post_mlsz_api({
            'type': 'getHeaderFilderData',
            'season': season,
            'federationId': '0',
            'leagueId': '-1',
            'changedType': 'first'
        })

        federations = init_data.get('federations', [])
        print(f"Found {len(federations)} federations.")

        for fed in federations:
            fed_id = str(fed['id'])
            fed_name = fed['name']

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
                        target_leagues.append({
                            "id": str(l['id']),
                            "name": l['name'].strip(),
                            "level": lvl,
                            "federation": fed_name,
                            "fed_id": fed_id
                        })
            except Exception as e:
                print(f"Failed to fetch leagues for federation {fed_name}: {e}", file=sys.stderr)

        print(f"Identified {len(target_leagues)} adult leagues across Hungary.")

        if args.limit_leagues:
            target_leagues = target_leagues[:args.limit_leagues]
            print(f"Limited to first {len(target_leagues)} leagues.")

    # Process each league
    for idx, l in enumerate(target_leagues, 1):
        lid = l['id']
        lname = l['name']
        fed_id = l['fed_id']
        fed_name = l['federation']
        level = l['level']

        print(f"[{idx}/{len(target_leagues)}] Scraping {lname} ({fed_name} - {level})...")

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

        league_match_count = 0
        for t in turns:
            turn_no = t.get('turn')
            matches = parse_round_matches(season, fed_id, lid, turn_no)
            for m in matches:
                # Geocode arena if not yet cached
                arena = m['vid']
                if arena and not args.skip_geocoding:
                    geocoder.geocode(arena, fed_name)
                match_dict[str(m['id'])] = m
                league_match_count += 1
            time.sleep(0.1)

        print(f"  -> Extracted {league_match_count} matches.")
        # Periodically persist venues
        geocoder.save()

    # Save all datasets
    geocoder.save()

    with open(LEAGUES_FILE, "w", encoding="utf-8") as f:
        json.dump(leagues_data, f, ensure_ascii=False, indent=2)

    all_matches_list = list(match_dict.values())
    # Sort matches by date then time
    all_matches_list.sort(key=lambda x: (x.get("d") or "9999", x.get("t") or "99:99"))

    with open(MATCHES_FILE, "w", encoding="utf-8") as f:
        json.dump(all_matches_list, f, ensure_ascii=False)

    with open(DATASET_JS_FILE, "w", encoding="utf-8") as f:
        f.write("window.MECCS_DATA = " + json.dumps({
            "leagues": leagues_data,
            "venues": geocoder.venues,
            "matches": all_matches_list
        }, ensure_ascii=False) + ";\n")

    print(f"\nDone! Saved:")
    print(f"  - {len(leagues_data)} leagues in {LEAGUES_FILE}")
    print(f"  - {len(geocoder.venues)} venues in {VENUES_FILE}")
    print(f"  - {len(all_matches_list)} matches in {MATCHES_FILE}")
    print(f"  - Combined bundle in {DATASET_JS_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MLSZ Football Matches Scraper")
    parser.add_argument("--test-league", type=str, help="Scrape single league ID (e.g. 33586 for OTP Bank Liga)")
    parser.add_argument("--limit-leagues", type=int, help="Limit number of leagues to scrape")
    parser.add_argument("--season", type=str, help="Override season ID (default: 67)")
    parser.add_argument("--fresh", action="store_true", help="Discard existing matches and scrape fresh")
    parser.add_argument("--skip-geocoding", action="store_true", help="Skip geocoding new venues")
    args = parser.parse_args()

    scrape(args)
