// Hungarian Football Matches Map Application
(function () {
  'use strict';

  let map;
  let markersLayer;
  let leaguesData = {};
  let venuesData = {};
  let matchesData = [];

  const dom = {
    globalSearch: document.getElementById('global-search'),
    levelSelect: document.getElementById('level-select'),
    leagueSelect: document.getElementById('league-select'),
    dateFrom: document.getElementById('date-from'),
    dateTo: document.getElementById('date-to'),
    presetBtns: document.querySelectorAll('.preset-btn'),
    timeSelect: document.getElementById('time-select'),
    resetBtn: document.getElementById('reset-filters-btn'),
    matchCount: document.getElementById('match-count'),
    loadingOverlay: document.getElementById('loading-overlay')
  };

  const TIER_CLASS_MAP = {
    'NB I': 'nbi',
    'NB II': 'nbii',
    'NB III': 'nbiii',
    'Megye I': 'megyei',
    'Megye II': 'megyeii',
    'Megye III': 'megyeiii',
    'Megye IV': 'megyeiv'
  };

  const TIER_PRIORITY = ['NB I', 'NB II', 'NB III', 'Megye I', 'Megye II', 'Megye III', 'Megye IV'];

  function createPitchIcon(level) {
    const tierClass = TIER_CLASS_MAP[level] || 'megyei';
    return L.divIcon({
      className: `custom-pitch-pin pin-${tierClass}`,
      html: '<span class="pitch-pin-icon">⚽</span>',
      iconSize: [26, 26],
      iconAnchor: [13, 13],
      popupAnchor: [0, -14]
    });
  }

  function debounce(fn, delay) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  function toYMD(d) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function initMap() {
    // Hungary center
    map = L.map('map', {
      center: [47.1625, 19.5033],
      zoom: 7.5,
      zoomSnap: 0.5,
      minZoom: 6,
      maxZoom: 18
    });

    // 1. Static predownloaded Hungary vector map (100% offline, zero network requests, no API key)
    const staticHungaryLayer = L.layerGroup();
    if (window.HUNGARY_GEOJSON) {
      const geoLayer = L.geoJSON(window.HUNGARY_GEOJSON, {
        style: function () {
          return {
            fillColor: '#dcedc8',
            fillOpacity: 0.85,
            color: '#2e7d32',
            weight: 1.5,
            dashArray: '3, 4'
          };
        },
        onEachFeature: function (feature, layer) {
          if (feature.properties && feature.properties.name) {
            layer.bindTooltip(feature.properties.name, {
              sticky: true,
              className: 'county-tooltip'
            });
          }
        }
      });
      staticHungaryLayer.addLayer(geoLayer);
    }

    // 2. Free Esri WorldStreetMap tile layer (no API key required, public worldwide CDN)
    const esriStreetLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, METI, TomTom'
    });

    // Set static predownloaded map as active default
    staticHungaryLayer.addTo(map);

    const baseMaps = {
      "🇭🇺 Statikus térkép (Előre letöltött, offline)": staticHungaryLayer,
      "🗺️ Részletes utcai térkép (Esri, ingyenes)": esriStreetLayer
    };

    L.control.layers(baseMaps, null, { position: 'topright' }).addTo(map);

    markersLayer = L.layerGroup().addTo(map);
  }

  async function loadData() {
    try {
      // 1. Check if dataset is preloaded via <script src="data/dataset.js"> (works on file:// and offline)
      if (window.MECCS_DATA && typeof window.MECCS_DATA === 'object') {
        leaguesData = window.MECCS_DATA.leagues || {};
        venuesData = window.MECCS_DATA.venues || {};
        matchesData = window.MECCS_DATA.matches || [];
      } else {
        // 2. Fallback to async JSON fetch
        const [leaguesRes, venuesRes, matchesRes] = await Promise.all([
          fetch('data/leagues.json').then(r => r.ok ? r.json() : {}),
          fetch('data/venues.json').then(r => r.ok ? r.json() : {}),
          fetch('data/matches.json').then(r => r.ok ? r.json() : [])
        ]);

        leaguesData = leaguesRes || {};
        venuesData = venuesRes || {};
        matchesData = Array.isArray(matchesRes) ? matchesRes : [];
      }

      updateLeagueDropdown();
      setupInitialDates();
      renderMarkers();
    } catch (err) {
      console.error('Error loading data:', err);
      const isFileProto = window.location.protocol === 'file:';
      const msg = isFileProto
        ? 'A böngésző helyi fájl védelme (CORS) miatt a meccsek betöltéséhez indíts webszervert:\npython3 -m http.server 8000\nmajd nyisd meg: http://localhost:8000'
        : 'Nem sikerült betölteni a meccsadatokat. Futtasd a scraper szkriptet:\npython scripts/scraper.py';
      alert(msg);
    } finally {
      if (dom.loadingOverlay) {
        dom.loadingOverlay.classList.remove('active');
      }
    }
  }

  function updateLeagueDropdown() {
    const selectedLevel = dom.levelSelect.value;
    const leaguesArray = Object.values(leaguesData);
    leaguesArray.sort((a, b) => (a.name || '').localeCompare(b.name || '', 'hu'));

    const filtered = selectedLevel === 'ALL'
      ? leaguesArray
      : leaguesArray.filter(l => l.level === selectedLevel);

    dom.leagueSelect.innerHTML = '<option value="ALL">Összes bajnokság</option>';

    filtered.forEach(l => {
      const opt = document.createElement('option');
      opt.value = l.id;
      opt.textContent = `${l.name} (${l.federation})`;
      dom.leagueSelect.appendChild(opt);
    });

    dom.leagueSelect.value = 'ALL';
  }

  function setDatePreset(preset) {
    if (!matchesData || matchesData.length === 0) return;
    const now = new Date();
    const todayStr = toYMD(now);

    if (preset === 'today') {
      dom.dateFrom.value = todayStr;
      dom.dateTo.value = todayStr;
    } else if (preset === 'weekend') {
      const day = now.getDay(); // 0: Sunday, 6: Saturday
      const sat = new Date(now);
      const sun = new Date(now);
      if (day === 0) {
        // Today is Sunday: cover this full weekend (Saturday to Sunday)
        sat.setDate(now.getDate() - 1);
        dom.dateFrom.value = toYMD(sat);
        dom.dateTo.value = todayStr;
      } else {
        const daysToSat = 6 - day;
        sat.setDate(now.getDate() + daysToSat);
        sun.setDate(now.getDate() + daysToSat + 1);
        dom.dateFrom.value = toYMD(sat);
        dom.dateTo.value = toYMD(sun);
      }
    } else if (preset === 'week') {
      const nextWeek = new Date(now);
      nextWeek.setDate(now.getDate() + 7);
      dom.dateFrom.value = todayStr;
      dom.dateTo.value = toYMD(nextWeek);
    } else if (preset === 'all') {
      dom.dateFrom.value = dom.dateFrom.min || '';
      dom.dateTo.value = dom.dateTo.max || '';
    }

    updatePresetButtons(preset);
    applyFilters();
  }

  function updatePresetButtons(activePreset) {
    dom.presetBtns.forEach(btn => {
      if (activePreset && btn.dataset.preset === activePreset) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }

  function setupInitialDates() {
    if (!matchesData || matchesData.length === 0) return;

    // Determine min/max available dates
    const dates = matchesData.map(m => m.d).filter(Boolean).sort();
    if (dates.length === 0) return;

    const minDate = dates[0];
    const maxDate = dates[dates.length - 1];

    dom.dateFrom.min = minDate;
    dom.dateFrom.max = maxDate;
    dom.dateTo.min = minDate;
    dom.dateTo.max = maxDate;

    const todayStr = toYMD(new Date());
    if (todayStr >= minDate && todayStr <= maxDate) {
      // Default to next 7 days so map opens fast with immediate upcoming matches
      setDatePreset('week');
    } else {
      setDatePreset('all');
    }
  }

  function onDateInput(e) {
    if (dom.dateFrom.value && dom.dateTo.value && dom.dateFrom.value > dom.dateTo.value) {
      if (e.target === dom.dateFrom) {
        dom.dateTo.value = dom.dateFrom.value;
      } else {
        dom.dateFrom.value = dom.dateTo.value;
      }
    }
    updatePresetButtons(null);
    applyFilters();
  }

  function applyFilters() {
    renderMarkers();
  }

  function renderMarkers() {
    markersLayer.clearLayers();

    const selectedLevel = dom.levelSelect.value;
    const selectedLeague = dom.leagueSelect.value;
    const searchQuery = dom.globalSearch.value.trim().toLowerCase();
    const fromDate = dom.dateFrom.value;
    const toDate = dom.dateTo.value;
    const timeFilter = dom.timeSelect ? dom.timeSelect.value : 'ALL';

    let visibleMatchCount = 0;
    // Group by unique coordinate key to prevent overlapping markers from occluding venues
    const locMap = new Map();

    matchesData.forEach(match => {
      const league = leaguesData[match.lid];
      const leagueLevel = league ? league.level : '';
      const leagueName = league ? league.name : '';

      // 1. Level filter (NB I, NB II, NB III, Megye I-IV)
      if (selectedLevel !== 'ALL' && leagueLevel !== selectedLevel) {
        return;
      }

      // 2. Specific league filter
      if (selectedLeague !== 'ALL' && String(match.lid) !== String(selectedLeague)) {
        return;
      }

      // 3. Date range filter
      if (fromDate) {
        if (!match.d || match.d < fromDate) return;
      }
      if (toDate) {
        if (!match.d || match.d > toDate) return;
      }

      // 4. Kick-off time filter
      if (timeFilter !== 'ALL') {
        const t = match.t;
        if (!t) return;
        const hr = parseInt(t.split(':')[0], 10);
        if (isNaN(hr)) return;
        if (timeFilter === 'morning' && hr >= 12) return;
        if (timeFilter === 'afternoon' && (hr < 12 || hr >= 17)) return;
        if (timeFilter === 'evening' && hr < 17) return;
      }

      // 5. Global search filter (teams, arena, town, league)
      if (searchQuery) {
        const venueInfo = venuesData[match.vid] || {};
        const haystack = (
          (match.h || '') + ' ' +
          (match.a || '') + ' ' +
          (match.vid || '') + ' ' +
          (venueInfo.address || '') + ' ' +
          leagueName + ' ' +
          leagueLevel
        ).toLowerCase();

        if (!haystack.includes(searchQuery)) {
          return;
        }
      }

      const venueKey = match.vid;
      if (!venueKey) return;

      const venueInfo = venuesData[venueKey];
      if (!venueInfo || typeof venueInfo.lat !== 'number' || typeof venueInfo.lng !== 'number') {
        return;
      }

      visibleMatchCount++;

      // Coordinate location key (rounded to 5 decimals ~1m)
      const locKey = `${venueInfo.lat.toFixed(5)},${venueInfo.lng.toFixed(5)}`;
      if (!locMap.has(locKey)) {
        locMap.set(locKey, {
          lat: venueInfo.lat,
          lng: venueInfo.lng,
          venues: new Map([[venueKey, venueInfo]]),
          matches: []
        });
      } else {
        locMap.get(locKey).venues.set(venueKey, venueInfo);
      }
      locMap.get(locKey).matches.push(match);
    });

    dom.matchCount.textContent = visibleMatchCount;

    // Plot grouped markers with tier-specific pin colors
    locMap.forEach(locGroup => {
      let pinTier = selectedLevel !== 'ALL' ? selectedLevel : 'Megye IV';
      if (selectedLevel === 'ALL') {
        for (const tier of TIER_PRIORITY) {
          if (locGroup.matches.some(m => {
            const l = leaguesData[m.lid];
            return l && l.level === tier;
          })) {
            pinTier = tier;
            break;
          }
        }
      }

      const marker = L.marker([locGroup.lat, locGroup.lng], { icon: createPitchIcon(pinTier) });
      const popupHtml = buildPopupContent(locGroup);
      marker.bindPopup(popupHtml, { maxWidth: 340 });
      markersLayer.addLayer(marker);
    });
  }

  function buildPopupContent(locGroup) {
    const venuesList = Array.from(locGroup.venues.values());
    const matches = locGroup.matches;

    // Sort matches chronologically
    matches.sort((a, b) => {
      const da = (a.d || '') + (a.t || '');
      const db = (b.d || '') + (b.t || '');
      return da.localeCompare(db);
    });

    const isMultiVenue = venuesList.length > 1;
    const venueTitle = venuesList.map(v => escapeHtml(v.name)).join(' / ');
    const venueAddress = venuesList[0].address ? escapeHtml(venuesList[0].address) : '';

    const matchesListHtml = matches.map(m => {
      const league = leaguesData[m.lid];
      const leagueName = league ? league.name : 'Bajnokság';
      const leagueLevel = league && league.level ? league.level : '';
      const tierClass = leagueLevel ? (TIER_CLASS_MAP[leagueLevel] || 'megyei') : '';
      const scoreHtml = m.s
        ? `<span class="match-score">${escapeHtml(m.s)}</span>`
        : `<span class="match-vs">vs</span>`;

      return `
        <div class="match-item">
          <div class="match-league-row">
            ${leagueLevel ? `<span class="match-level-badge badge-${tierClass}">${escapeHtml(leagueLevel)}</span>` : ''}
            <span class="match-league-tag">${escapeHtml(leagueName)}</span>
            ${isMultiVenue && m.vid ? `<span class="match-arena-tag">${escapeHtml(m.vid)}</span>` : ''}
          </div>
          <div class="match-time-row">
            <span>📅 ${escapeHtml(m.d || 'Időpont nélkül')}</span>
            <span>⏰ ${escapeHtml(m.t ? m.t : 'TBD')}</span>
          </div>
          <div class="match-teams-row">
            <span class="match-team home">${escapeHtml(m.h)}</span>
            ${scoreHtml}
            <span class="match-team away">${escapeHtml(m.a)}</span>
          </div>
        </div>
      `;
    }).join('');

    const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${locGroup.lat},${locGroup.lng}`;

    return `
      <div class="popup-card">
        <div class="popup-header">
          <div class="popup-venue-name">${venueTitle}</div>
          ${venueAddress ? `<div class="popup-venue-address">${venueAddress}</div>` : ''}
        </div>
        <div class="popup-matches-list">
          ${matchesListHtml}
        </div>
        <div class="popup-footer">
          <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="directions-link">📍 Útvonaltervezés Google Térképen &rarr;</a>
        </div>
      </div>
    `;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function resetFilters() {
    dom.globalSearch.value = '';
    dom.levelSelect.value = 'ALL';
    if (dom.timeSelect) dom.timeSelect.value = 'ALL';
    updateLeagueDropdown();
    setupInitialDates();
    renderMarkers();
  }

  function initEvents() {
    const debouncedFilter = debounce(applyFilters, 200);

    dom.levelSelect.addEventListener('change', () => {
      updateLeagueDropdown();
      applyFilters();
    });

    dom.globalSearch.addEventListener('input', debouncedFilter);
    dom.leagueSelect.addEventListener('change', applyFilters);

    dom.presetBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        setDatePreset(btn.dataset.preset);
      });
    });

    if (dom.timeSelect) {
      dom.timeSelect.addEventListener('change', applyFilters);
    }

    dom.dateFrom.addEventListener('input', onDateInput);
    dom.dateFrom.addEventListener('change', onDateInput);
    dom.dateTo.addEventListener('input', onDateInput);
    dom.dateTo.addEventListener('change', onDateInput);

    dom.resetBtn.addEventListener('click', resetFilters);
  }

  // Initialize
  initMap();
  initEvents();
  loadData();
})();
