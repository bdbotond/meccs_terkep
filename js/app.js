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
    resetBtn: document.getElementById('reset-filters-btn'),
    matchCount: document.getElementById('match-count'),
    loadingOverlay: document.getElementById('loading-overlay')
  };

  // Football pin icon
  const pitchIcon = L.divIcon({
    className: 'custom-pitch-pin',
    html: '⚽',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -14]
  });

  function initMap() {
    // Hungary center
    map = L.map('map', {
      center: [47.1625, 19.5033],
      zoom: 7.5,
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

      populateLeagues();
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

  function populateLeagues() {
    updateLeagueDropdown();

    // Event: level selection change
    dom.levelSelect.addEventListener('change', () => {
      updateLeagueDropdown();
      applyFilters();
    });

    // Event: live search typing
    dom.globalSearch.addEventListener('input', () => {
      applyFilters();
    });
  }

  function updateLeagueDropdown() {
    const selectedLevel = dom.levelSelect.value;
    const leaguesArray = Object.values(leaguesData);
    leaguesArray.sort((a, b) => a.name.localeCompare(b.name, 'hu'));

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

    // Default: full current season so all scraped matches are visible
    dom.dateFrom.value = minDate;
    dom.dateTo.value = maxDate;
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

    let visibleMatchCount = 0;
    const venueMatchesMap = new Map();

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
      if (fromDate && match.d && match.d < fromDate) {
        return;
      }
      if (toDate && match.d && match.d > toDate) {
        return;
      }

      // 4. Global search filter (teams, arena, town, league)
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

      if (!venueMatchesMap.has(venueKey)) {
        venueMatchesMap.set(venueKey, {
          venue: venueInfo,
          matches: []
        });
      }
      venueMatchesMap.get(venueKey).matches.push(match);
    });

    dom.matchCount.textContent = visibleMatchCount;

    // Plot markers
    venueMatchesMap.forEach(({ venue, matches }) => {
      const marker = L.marker([venue.lat, venue.lng], { icon: pitchIcon });
      const popupHtml = buildPopupContent(venue, matches);
      marker.bindPopup(popupHtml, { maxWidth: 330 });
      markersLayer.addLayer(marker);
    });
  }

  function buildPopupContent(venue, matches) {
    // Sort matches chronologically
    matches.sort((a, b) => {
      const da = (a.d || '') + (a.t || '');
      const db = (b.d || '') + (b.t || '');
      return da.localeCompare(db);
    });

    const matchesListHtml = matches.map(m => {
      const league = leaguesData[m.lid];
      const leagueName = league ? league.name : 'Bajnokság';
      const leagueLevel = league && league.level ? league.level : '';
      const scoreHtml = m.s
        ? `<span class="match-score">${escapeHtml(m.s)}</span>`
        : `<span class="match-vs">vs</span>`;

      return `
        <div class="match-item">
          <div class="match-league-row">
            ${leagueLevel ? `<span class="match-level-badge">${escapeHtml(leagueLevel)}</span>` : ''}
            <span class="match-league-tag">${escapeHtml(leagueName)}</span>
          </div>
          <div class="match-time-row">
            <span>📅 ${m.d || 'Időpont nélkül'}</span>
            <span>⏰ ${m.t ? m.t : 'TBD'}</span>
          </div>
          <div class="match-teams-row">
            <span class="match-team home">${escapeHtml(m.h)}</span>
            ${scoreHtml}
            <span class="match-team away">${escapeHtml(m.a)}</span>
          </div>
        </div>
      `;
    }).join('');

    const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${venue.lat},${venue.lng}`;

    return `
      <div class="popup-card">
        <div class="popup-header">
          <div class="popup-venue-name">${escapeHtml(venue.name)}</div>
          <div class="popup-venue-address">${escapeHtml(venue.address || '')}</div>
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
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function resetFilters() {
    dom.globalSearch.value = '';
    dom.levelSelect.value = 'ALL';
    updateLeagueDropdown();
    setupInitialDates();
    renderMarkers();
  }

  // Event Listeners
  dom.leagueSelect.addEventListener('change', applyFilters);
  dom.dateFrom.addEventListener('change', applyFilters);
  dom.dateTo.addEventListener('change', applyFilters);
  dom.resetBtn.addEventListener('click', resetFilters);

  // Initialize
  initMap();
  loadData();
})();
