# Magyar Foci Meccstérkép 

[Kipróbálható Itt](https://bdbotond.github.io/meccs_terkep/)


Interaktív térkép az összes magyar felnőtt labdarúgó-mérkőzés megjelenítésére (NB I, NB II, NB III, Megye/Vármegye I-IV) pontos helyszínnel, kezdési időponttal és csapatokkal.

Adatforrás: [MLSZ Adatbank](https://adatbank.mlsz.hu)

---

## TODO

- [ ] Naptár import készítése
- [ ] Más magyar spotokat is hozzáadni

## Mit tud

- **Interaktív térkép**: Magyarország térképén megjelenő meccshelyszínek és stadionok (előre letöltött offline vektoros térkép + opcionális Esri utcatérkép).
- **Bajnokság szerinti szűrés**: Külön választó az osztályokhoz: NB I, NB II, NB III, Megye I, Megye II, Megye III, Megye IV.
- **Csapat keresés**: Keresés csapatok és ligák szerint.
- **Dátum intervallum szűrő**:  `Kezdő dátum` és `Utolsó dátum`-mal idopontra szürés
- **Részletes meccsleírás**:
  - Osztály és bajnokság
  - Dátum és kezdési időpont
  - Csapatok (Hazai vs Vendég)
  - Eredmény (befejezett mérkőzés esetén)
  - Egy kattintásos Google Térkép útvonaltervezés a helyszínhez
  
- **Heti automatikus frissítés**: GitHub Actions munkafolyamat minden hétfőn 04:00-kor lefut, ellenőrzi a menetrend változásait és szükség esetén automatikusan elmenti a frissítéseket a repóba.

---

## Adatstruktúra

A frontend minimális hálózati terhelés mellett (`~1 MB` tömörítve) azonnali, kliensoldali szűrést biztosít a normalizált JSON fájlok segítségével:

- `data/leagues.json`: Bajnokságok (ID, megnevezés, szint, igazgatóság)
- `data/venues.json`: Pályák és stadionok geokódolt GPS koordinátákkal és címekkel (OpenStreetMap / Photon)
- `data/matches.json`: Szezon mérkőzései (időpont, liga, pálya, hazai csapat, vendég csapat, eredmény)

---

## Futtatás

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
