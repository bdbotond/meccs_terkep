# Magyar Foci Meccstérkép (Hungarian Football Matches Map)

Interaktív webes térkép az összes magyar felnőtt labdarúgó-mérkőzés megjelenítésére (NB I, NB II, NB III, Megye/Vármegye I-IV) pontos helyszínnel, kezdési időponttal és csapatokkal.

Adatforrás: [MLSZ Adatbank](https://adatbank.mlsz.hu)

---

## Fő funkciók

- **Interaktív Leaflet térkép**: Magyarország térképén megjelenő meccshelyszínek és stadionok (előre letöltött offline vektoros térkép + opcionális Esri utcatérkép).
- **Szint szerinti szűrés**: Külön választó az osztályokhoz: NB I, NB II, NB III, Megye I / BLSZ I, Megye II, Megye III, Megye IV.
- **Bajnokság választó**: Dinamikus legördülő lista az adott szinthez tartozó bajnokságok szűréséhez.
- **Azonnali globális keresés**: Valós idejű keresőmező csapatok, stadionok, települések és ligák szerint.
- **Dátum intervallum szűrő**: Natív HTML5 `Kezdő dátum` és `Záró dátum` mezők a kívánt időszak kiválasztásához.
- **Részletes meccskártyák**:
  - Osztály és bajnokság jelvény
  - Dátum és kezdési időpont
  - Csapatok (Hazai vs Vendég)
  - Eredmény (befejezett mérkőzés esetén) vagy vs jelzés
  - Egy kattintásos Google Térkép útvonaltervezés a helyszínhez
- **Inkrementális adatbázis-frissítés**: Csak a megváltozott értékeket írja felül (időpont, pálya, eredmény), nem törli a meglévő meccseket.
- **Heti automatikus frissítés**: GitHub Actions munkafolyamat minden hétfőn 04:00-kor lefut, ellenőrzi a menetrend változásait és szükség esetén automatikusan elmenti a frissítéseket a repóba.

---

## Adatstruktúra

A frontend minimális hálózati terhelés mellett (`~1 MB` tömörítve) azonnali, kliensoldali szűrést biztosít a normalizált JSON fájlok segítségével:

- `data/leagues.json`: Bajnokságok (ID, megnevezés, szint, igazgatóság)
- `data/venues.json`: Pályák és stadionok geokódolt GPS koordinátákkal és címekkel (OpenStreetMap / Photon)
- `data/matches.json`: Szezon mérkőzései (időpont, liga, pálya, hazai csapat, vendég csapat, eredmény)

---

## Helyi futtatás

A weboldal tisztán statikus (HTML, CSS, Vanilla JS), így bármilyen helyi webszerverrel azonnal elindítható:

```bash
# Python beépített webszerver indítása
python3 -m http.server 8000
```

Ezután nyisd meg a böngészőben: `http://localhost:8000`

---

## Scraper manuális futtatása

A meccsadatok és helyszínek frissítéséhez:

```bash
# Virtuális környezet és függőségek telepítése
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Teszt futtatás csak az NB I-re:
python scripts/scraper.py --test-league 33586

# Első 5 bajnokság letöltése:
python scripts/scraper.py --limit-leagues 5

# Teljes országos adatbázis letöltése (összes felnőtt bajnokság):
python scripts/scraper.py --full
```

---

## GitHub Pages & GitHub Actions beállítása

1. **GitHub Pages engedélyezése**:
   - Menj a repository beállításaihoz: **Settings** -> **Pages**.
   - A **Build and deployment** résznél válaszd ki: **Deploy from a branch**.
   - Branch: `main`, könyvtár: `/ (root)`.
2. **GitHub Actions írási jog**:
   - Menj a **Settings** -> **Actions** -> **General** -> **Workflow permissions** menüpontba.
   - Válaszd ki: **Read and write permissions** (hogy a hétfői cron commitolni tudja a megváltozott meccsadatokat).

---

## TODO

- [ ] Online elérhetőség
- [ ] Naptár import készítése
- [ ] Más magyar spotokat is hozzáadni
