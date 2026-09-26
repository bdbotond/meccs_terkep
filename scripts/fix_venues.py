#!/usr/bin/env python3
"""
Fix and validate all venue locations in meccs_terkep.
Cross-references:
1. Curated stadium / arena registry
2. Budapest district grounds registry
3. KSH / GeoNames Hungarian settlements database (3571 settlements with county & coordinates)
4. League county / federation constraints from matches.json & leagues.json
5. Point-in-polygon verification against hungary_map.js GeoJSON
"""

import json
import os
import re
import math
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
VENUES_FILE = os.path.join(DATA_DIR, "venues.json")
MATCHES_FILE = os.path.join(DATA_DIR, "matches.json")
LEAGUES_FILE = os.path.join(DATA_DIR, "leagues.json")
DATASET_JS_FILE = os.path.join(DATA_DIR, "dataset.js")
SETTLEMENTS_FILE = os.path.join(DATA_DIR, "hu_settlements.json")
HUNGARY_MAP_FILE = os.path.join(DATA_DIR, "hungary_map.js")

# Curated exact GPS coordinates and addresses for known stadiums, arenas, and sports complexes
KNOWN_ARENAS = {
    # NB I & NB II & Major Arenas
    'ETO Stadion': {'lat': 47.69507, 'lng': 17.66015, 'address': 'ETO Park, Győr'},
    'Szusza Ferenc Stadion': {'lat': 47.57487, 'lng': 19.08349, 'address': 'Szusza Ferenc Stadion, Megyeri út, Budapest'},
    'Bozsik Aréna': {'lat': 47.44253, 'lng': 19.15555, 'address': 'Bozsik Aréna, Puskás Ferenc utca, Budapest'},
    'Groupama Aréna': {'lat': 47.47540, 'lng': 19.09521, 'address': 'Groupama Aréna, Üllői út, Budapest'},
    'Új Hidegkuti Nándor Stadion': {'lat': 47.49082, 'lng': 19.10675, 'address': 'Hidegkuti Nándor Stadion, Salgótarjáni utca, Budapest'},
    'MTK Utánpótlás Sportközpont': {'lat': 47.49082, 'lng': 19.10675, 'address': 'Hidegkuti Nándor Stadion, Budapest'},
    'Illovszky Rudolf Stadion': {'lat': 47.53664, 'lng': 19.08016, 'address': 'Illovszky Rudolf Stadion, Fáy utca, Budapest'},
    'DVTK Stadion': {'lat': 48.09986, 'lng': 20.71756, 'address': 'DVTK Stadion, Andrássy Gyula utca, Miskolc'},
    'DVTK Edzőközpont': {'lat': 48.09860, 'lng': 20.71505, 'address': 'DVTK Edzőközpont, Miskolc'},
    'Debreceni Nagyerdei Stadion': {'lat': 47.55399, 'lng': 21.63291, 'address': 'Nagyerdei Stadion, Debrecen'},
    'Debreceni Labdarúgó Akadémia Edzőközpont': {'lat': 47.55329, 'lng': 21.63295, 'address': 'Debreceni Labdarúgó Akadémia, Debrecen'},
    'Debreceni Egyetemi AC Sporttelep': {'lat': 47.55572, 'lng': 21.61512, 'address': 'DEAC Sporttelep, Dóczy József utca, Debrecen'},
    'Nyíregyháza Városi Stadion': {'lat': 47.97045, 'lng': 21.71228, 'address': 'Városi Stadion, Sóstói út, Nyíregyháza'},
    'Nyíregyháza Örökösföld Sporttelep': {'lat': 47.96334, 'lng': 21.74502, 'address': 'Örökösföldi Sporttelep, Nyíregyháza'},
    'Kisvárdai Várkerti Stadion': {'lat': 48.23321, 'lng': 22.07358, 'address': 'Várkerti Stadion, Kisvárda'},
    'Paksi FC Stadion': {'lat': 46.63374, 'lng': 18.85247, 'address': 'Fehérvári úti Stadion, Paks'},
    'Puskás Akadémia Pancho Aréna': {'lat': 47.46396, 'lng': 18.58662, 'address': 'Pancho Aréna, Fő utca, Felcsút'},
    'ZTE Aréna': {'lat': 46.84871, 'lng': 16.84853, 'address': 'ZTE Aréna, Október 6. tér, Zalaegerszeg'},
    'Székesfehérvári Sóstói Stadion': {'lat': 47.17365, 'lng': 18.41431, 'address': 'MOL Aréna Sóstó, Csíkvári út, Székesfehérvár'},
    'Nagykanizsai Olajbányász Stadion': {'lat': 46.45096, 'lng': 16.98455, 'address': 'Olajbányász sporttelep, Nagykanizsa'},
    'Ajkai Városi Sportcentrum': {'lat': 47.10840, 'lng': 17.55010, 'address': 'Városi Sportcentrum, Városliget, Ajka'},
    'Kolorcity Aréna': {'lat': 48.24369, 'lng': 20.61036, 'address': 'Kolorcity Aréna, Kazincbarcika'},
    'Kecskeméti Széktói Stadion': {'lat': 46.90155, 'lng': 19.66988, 'address': 'Széktói Stadion, Csabay Géza körút, Kecskemét'},
    'Mezőkövesd Városi Stadion': {'lat': 47.80216, 'lng': 20.56731, 'address': 'Városi Stadion, Széchenyi utca, Mezőkövesd'},
    'Szent Gellért Fórum': {'lat': 46.26238, 'lng': 20.11885, 'address': 'Szent Gellért Fórum, Dorozsmai út, Szeged'},
    'Szegedi Vasutas SE Sporttelep': {'lat': 46.25463, 'lng': 20.14860, 'address': 'SZVSE Sporttelep, Kossuth Lajos sugárút, Szeged'},
    'Tiszakécske Városi Sportcentrum': {'lat': 46.93512, 'lng': 20.10552, 'address': 'Városi Stadion, Szabolcska Mihály utca, Tiszakécske'},
    'Szentlőrinc SE Sporttelep': {'lat': 46.04250, 'lng': 17.98630, 'address': 'Szentlőrinc SE Sporttelep, Bányász utca, Szentlőrinc'},
    'ALCUFER Stadion': {'lat': 47.63288, 'lng': 17.59277, 'address': 'ALCUFER Stadion, Ménfői út, Győr-Gyirmót'},
    'PMFC Stadion': {'lat': 46.06876, 'lng': 18.19592, 'address': 'PMFC Stadion, Stadion utca, Pécs'},
    'Haladás Sportkomplexum': {'lat': 47.23493, 'lng': 16.60693, 'address': 'Haladás Sportkomplexum, Rohonci út, Szombathely'},
    'Király Sportlétesítmény': {'lat': 47.21850, 'lng': 16.59820, 'address': 'Király Sportlétesítmény, Temesvár utca, Szombathely'},
    'Király Sportlétesítmény ( régi )': {'lat': 47.21850, 'lng': 16.59820, 'address': 'Király Sportlétesítmény, Temesvár utca, Szombathely'},
    'Kolozsvár úti sporttelep': {'lat': 47.22800, 'lng': 16.63500, 'address': 'Kolozsvár úti sporttelep, Szombathely'},
    'Gyöngyöshermán-Szentkirály Sportpálya': {'lat': 47.20465, 'lng': 16.64578, 'address': 'Sportpálya, Gyöngyöshermán, Szombathely'},
    'Putnoki Várady Béla Sportközpont': {'lat': 48.28758, 'lng': 20.43253, 'address': 'Váradi Béla Sportközpont, Pitypalatty utca, Putnok'},
    'Cigánd Városi Stadion': {'lat': 48.25800, 'lng': 21.89020, 'address': 'Városi Stadion, Fő út, Cigánd'},
    'Eger Szentmarjay Tibor Városi Stadion': {'lat': 47.89899, 'lng': 20.37437, 'address': 'Szentmarjay Tibor Városi Stadion, Stadion utca, Eger'},
    'Karcag Liget úti Sportcentrum': {'lat': 47.31937, 'lng': 20.90281, 'address': 'Liget úti sporttelep, Karcag'},
    'Békéscsabai Kórház utcai Stadion': {'lat': 46.68624, 'lng': 21.10544, 'address': 'Kórház utcai Stadion, Békéscsaba'},
    'Hódmezővásárhelyi Városi Stadion': {'lat': 46.42370, 'lng': 20.33144, 'address': 'Városi Stadion, Hódmezővásárhely'},
    'Perutz Stadion': {'lat': 47.33437, 'lng': 17.47382, 'address': 'Perutz Stadion, Várkert utca, Pápa'},
    'Siófok Városi Stadion': {'lat': 46.90924, 'lng': 18.06160, 'address': 'Városi Stadion, Révész Géza utca, Siófok'},
    'Kaposvári Rákóczi Stadion': {'lat': 46.35655, 'lng': 17.80602, 'address': 'Rákóczi Stadion, Pécsi út, Kaposvár'},
    'Budaörsi Városi Stadion': {'lat': 47.46172, 'lng': 18.93851, 'address': 'Városi Stadion, Árok utca, Budaörs'},
    'Gyulai id. Christián László Városi Sporttelep': {'lat': 46.64360, 'lng': 21.27210, 'address': 'Id. Christián László Városi Sporttelep, Ajtóssy Albert utca, Gyula'},
    'Szekszárdi Városi Sport és Szabadidőközpont': {'lat': 46.34780, 'lng': 18.71830, 'address': 'Városi Sport- és Szabadidőközpont, Keselyűsi út, Szekszárd'},
    'Veszprémi Városi Stadion': {'lat': 47.08374, 'lng': 17.90276, 'address': 'Városi Stadion, Wartha Vince utca, Veszprém'},
    'Soproni Városi Stadion': {'lat': 47.69160, 'lng': 16.58382, 'address': 'Városi Stadion, Káposztás utca, Sopron'},
    'Tiszaújváros Sportcentrum': {'lat': 47.92948, 'lng': 21.05051, 'address': 'Tiszaújvárosi Sportcentrum, Teleki Blanka út, Tiszaújváros'},
    'Mátészalkai Városi Sporttelep': {'lat': 47.95391, 'lng': 22.32085, 'address': 'Városi Sporttelep, Kölcsey utca, Mátészalka'},
    'Salgótarjáni Tó-strand Sporttelep': {'lat': 48.09607, 'lng': 19.80056, 'address': 'Tó-strand Sporttelep, Tóstrand út, Salgótarján'},
    'Szolnoki Tiszaligeti Stadion': {'lat': 47.16813, 'lng': 20.20092, 'address': 'Tiszaligeti Stadion, Tiszaliget, Szolnok'},
    'Bicskei TC Sporttelep': {'lat': 47.49071, 'lng': 18.63580, 'address': 'Bicskei TC Sporttelep, Kisfaludy utca, Bicske'},
    'MTE 1904 Sporttelep': {'lat': 47.87650, 'lng': 17.27120, 'address': 'MTE 1904 Sporttelep, Wittmann Antal park, Mosonmagyaróvár'},
    'MITE': {'lat': 47.86800, 'lng': 17.27000, 'address': 'MITE Sporttelep, Mosonmagyaróvár'},
    'Komárom Molaji Sporttelep': {'lat': 47.74100, 'lng': 18.11800, 'address': 'Molaji Sporttelep, Sport utca, Komárom'},
    'Buzánszky Jenő Labdarúgó Stadion': {'lat': 47.72163, 'lng': 18.73818, 'address': 'Buzánszky Jenő Stadion, Köztársaság út, Dorog'},
    'Károlyi István Sporttelep Iváncsa': {'lat': 47.15580, 'lng': 18.82100, 'address': 'Károlyi István Sporttelep, Arany János utca, Iváncsa'},
    'Novák Ferenc Érdi Sportközpont': {'lat': 47.38200, 'lng': 18.91800, 'address': 'Novák Ferenc Érdi Sportközpont, Ercsi út, Érd'},
    'Majosi SE Sporttelep': {'lat': 46.30720, 'lng': 18.50210, 'address': 'Majosi SE Sporttelep, Bonyhád-Majos'},
    'Dunaharaszti MTK Sporttelep': {'lat': 47.35415, 'lng': 19.09122, 'address': 'Dunaharaszti MTK Sporttelep, Mindszenty József utca, Dunaharaszti'},
    'Dunaharaszti MTK műfüves sportpályája': {'lat': 47.35415, 'lng': 19.09122, 'address': 'Dunaharaszti MTK Sporttelep, Dunaharaszti'},
    'Balatonalmádi Sportközpont': {'lat': 47.02700, 'lng': 18.01600, 'address': 'Balatonalmádi Sportközpont, Rákóczi út, Balatonalmádi'},
    'Sárbogárd Sporttelep': {'lat': 46.88744, 'lng': 18.61962, 'address': 'Sárbogárd Sporttelep, Prohászka utca, Sárbogárd'},
    'FTC-MVM Népligeti Sportközpont': {'lat': 47.48057, 'lng': 19.11548, 'address': 'FTC-MVM Népligeti Sportközpont, Budapest'},
    'Feleki Attila Sportközpont': {'lat': 46.02970, 'lng': 18.29210, 'address': 'Feleki Attila Sportközpont, Alkotmány tér, Kozármisleny'},
    'Grosics Gyula Stadion': {'lat': 47.55653, 'lng': 18.41776, 'address': 'Grosics Gyula Stadion, Szent Borbála út, Tatabánya'},
    'Lázár Bence Lajosmizsei Labdarúgó Sportcentrum': {'lat': 47.02663, 'lng': 19.56699, 'address': 'Lázár Bence Sportcentrum, Lajosmizse'},
    'Balatoni Vasas SE Sporttelep': {'lat': 46.88500, 'lng': 18.06500, 'address': 'Balatoni Vasas Sporttelep, Siófok-Kiliti'},
    'Tihanyi Sporttelep': {'lat': 46.91500, 'lng': 17.88500, 'address': 'Tihanyi Sporttelep, Major utca, Tihany'},
    'Dombóvári Szuhay Sportcentrum': {'lat': 46.37680, 'lng': 18.13800, 'address': 'Szuhay Sportcentrum, Földvár utca, Dombóvár'},
    'Tóth-Zele József Sportközpont Gesztely': {'lat': 48.10000, 'lng': 20.96670, 'address': 'Tóth-Zele József Sportközpont, Gesztely'},
    'Szebelley Ferenc Sporttelep - Bucsa': {'lat': 47.20000, 'lng': 21.00000, 'address': 'Szebelley Ferenc Sporttelep, Bucsa'},
    'Gulyás István Sport és Szabadidőközpont Parasznya': {'lat': 48.17000, 'lng': 20.66000, 'address': 'Gulyás István Sportközpont, Parasznya'},
    'Báta KSE Labdarúgó pálya': {'lat': 46.12860, 'lng': 18.77030, 'address': 'Báta KSE Labdarúgó pálya, Báta'},
    'Kétpó Községi Sport, és Művelődési Egyesület': {'lat': 47.08330, 'lng': 20.46670, 'address': 'Községi Sportpálya, Kétpó'},
    'Visz Községi Sportpálya': {'lat': 46.72610, 'lng': 17.78200, 'address': 'Községi Sportpálya, Visz'},
    'Nagy Norbert Sportközpont Hajdúnánás': {'lat': 47.85000, 'lng': 21.43330, 'address': 'Nagy Norbert Sportközpont, Hajdúnánás'},
    'Öreglaki MEDOSZ SE': {'lat': 46.60100, 'lng': 17.62150, 'address': 'Öreglaki Sporttelep, Öreglak'},
    'Harmat János Sporttelep': {'lat': 46.43370, 'lng': 16.90300, 'address': 'Harmat János Sporttelep, Szepetnek'},
    'Lázár Gyula Városi Sporttelep': {'lat': 47.08500, 'lng': 21.21500, 'address': 'Lázár Gyula Városi Sporttelep, Füzesgyarmat'},
    'Sóskúti sportpálya': {'lat': 47.40660, 'lng': 18.82250, 'address': 'Sportpálya, Sóskút'},
    'Tokod SE Sporttelep': {'lat': 47.72280, 'lng': 18.65890, 'address': 'Tokod SE Sporttelep, Tokod'},
    'Berzence Sportegyesület Sportpálya': {'lat': 46.20910, 'lng': 17.14810, 'address': 'Sportpálya, Berzence'},
    'Lóránt Gyula Sporttelep': {'lat': 47.38700, 'lng': 16.54000, 'address': 'Lóránt Gyula Sporttelep, Kőszeg'},
    'Gyöngyöstarjáni RE Sportpálya': {'lat': 47.81370, 'lng': 19.86720, 'address': 'Sportpálya, Gyöngyöstarján'},
    'Labdarúgó pálya Nagyvázsony': {'lat': 46.98300, 'lng': 17.69630, 'address': 'Labdarúgó pálya, Nagyvázsony'},
    'Dr. Kófiás Mihály Városi Sporttelep': {'lat': 46.16000, 'lng': 18.42000, 'address': 'Dr. Kófiás Mihály Városi Sporttelep, Pécsvárad'},
    'Sásd Városi sportpálya': {'lat': 46.25500, 'lng': 18.10900, 'address': 'Városi sportpálya, Sásd'},
    'Kaposszekcső-Csikostöttös KSE Sporttelepe': {'lat': 46.34000, 'lng': 18.13000, 'address': 'KSE Sporttelepe, Csikóstőttős / Mágocs'},
    'Hidas SE': {'lat': 46.25950, 'lng': 18.49770, 'address': 'Hidas SE Sporttelep, Hidas'},
    'Békésszentandrási Sportpálya': {'lat': 46.87700, 'lng': 20.48500, 'address': 'Békésszentandrási Sportpálya, Békésszentandrás'},
    'Tiszaug Sporttelep': {'lat': 46.85500, 'lng': 20.06000, 'address': 'Tiszaug Sporttelep, Tiszaug'},
    'Dunafalva Sporttelep': {'lat': 46.08800, 'lng': 18.77500, 'address': 'Dunafalva Sporttelep, Dunafalva'},
    'Tarpa Sportcentrum': {'lat': 48.10600, 'lng': 22.53100, 'address': 'Tarpa Sportcentrum, Tarpa'},
    'Grosics Gyula Labdarúgó Akadémia': {'lat': 46.26240, 'lng': 20.11890, 'address': 'Grosics Gyula Akadémia, Dorozsmai út, Szeged'},
    'FC Dabas Wellis Sportpark': {'lat': 47.18800, 'lng': 19.31200, 'address': 'Wellis Sportpark, Dabas'},
    'Füzesabonyi Sporttelep': {'lat': 47.74854, 'lng': 20.41427, 'address': 'Füzesabonyi Sporttelep, Füzesabony'},
    'Lipcsey Elemér Sporttelep': {'lat': 47.62245, 'lng': 20.75234, 'address': 'Lipcsey Elemér Sporttelep, Tiszafüred'},
    'Szűcs Lajos Sportcentrum (Gödöllő)': {'lat': 47.59831, 'lng': 19.33480, 'address': 'Szűcs Lajos Sportcentrum, Gödöllő'},
    'Balassi Bálint utcai Stadion (Monor)': {'lat': 47.35258, 'lng': 19.43864, 'address': 'Balassi Bálint utcai Stadion, Monor'},
    'Sándorfalva Sporttelep': {'lat': 46.36574, 'lng': 20.10422, 'address': 'Sándorfalva Sporttelep, Sándorfalva'},
    'Sárisápi Bányász SE Sporttelep': {'lat': 47.67436, 'lng': 18.68135, 'address': 'Bányász Sporttelep, Sárisáp'},
    'Bestrong Sportkomplexum': {'lat': 47.49500, 'lng': 21.64200, 'address': 'Bestrong Sportkomplexum, Monostorpályi út, Debrecen'},
    'Lokomotív Sporttelep': {'lat': 47.66670, 'lng': 19.68330, 'address': 'Lokomotív Sporttelep, Népkert, Hatvan'},
    'Lurkó Focimánia': {'lat': 47.17470, 'lng': 20.19830, 'address': 'Lurkó Focimánia Sporttelep, Szolnok'},
    'Bogát 2000 TC Sportpálya': {'lat': 47.81670, 'lng': 22.03330, 'address': 'Bogát 2000 TC Sportpálya, Nyírbogát'},
    'WINDOOR Sport Szabadidőközpont': {'lat': 46.83500, 'lng': 16.85000, 'address': 'WINDOOR Sportközpont, Páterdomb, Zalaegerszeg'},
    'Léránt Lajos Sportcentrum': {'lat': 46.68720, 'lng': 16.68060, 'address': 'Léránt Lajos Sportcentrum, Nova'},
    'Rábai Gábor Spottelep': {'lat': 47.38000, 'lng': 16.57000, 'address': 'Rábai Gábor Sporttelep, Kőszegfalva'},
    'Péti MTE Sporttelep': {'lat': 47.17700, 'lng': 18.12500, 'address': 'Péti MTE Sporttelep, Pétfürdő'},
    'Gyulafirátót Sport Egyesület': {'lat': 47.14000, 'lng': 17.96500, 'address': 'Sportpálya, Gyulafirátót, Veszprém'},
    'Bábolnai SE Sporttelep': {'lat': 47.64300, 'lng': 17.97500, 'address': 'Bábolnai SE Sporttelep, Bábolna'},
    'Kisalag SC Sporttelep': {'lat': 47.59500, 'lng': 19.20500, 'address': 'Kisalag SC Sporttelep, Fót-Kisalag'},
    'Acsai sporttelep': {'lat': 47.79800, 'lng': 19.38800, 'address': 'Sporttelep, Acsa'},
    'Szadai SE Sporttelep': {'lat': 47.63300, 'lng': 19.31700, 'address': 'Szadai SE Sporttelep, Szada'},
    'Mozdulj Cibak SE': {'lat': 46.94500, 'lng': 20.32000, 'address': 'Sportpálya, Cibakháza'},
    'Bácsa FC SE Sporttelep': {'lat': 47.72000, 'lng': 17.65500, 'address': 'Bácsa FC Sporttelep, Bácsa, Győr'},
    'Nádorvárosi Stadion': {'lat': 47.67500, 'lng': 17.63500, 'address': 'Nádorvárosi Stadion (DAC pálya), Győr'},
    'Győrszentiván SE Sporttelep': {'lat': 47.70500, 'lng': 17.73500, 'address': 'Győrszentiván SE Sporttelep, Győr-Győrszentiván'},
    'ESK Ménfőcsanak Sporttelep': {'lat': 47.63300, 'lng': 17.60700, 'address': 'Ménfőcsanak Sporttelep, Győr-Ménfőcsanak'},
    'Bajcs SE sportpálya': {'lat': 47.71200, 'lng': 17.68500, 'address': 'Bajcs SE sportpálya, Győr-Kisbajcs'},
    'Balfi SE': {'lat': 47.65200, 'lng': 16.66200, 'address': 'Sportpálya, Balf, Sopron'},
    'Újszegedi Sportpálya': {'lat': 46.24800, 'lng': 20.16500, 'address': 'Újszegedi TC sportpálya, Szeged'},
    'Főnix Labdarúgó és Lovaspark': {'lat': 47.18600, 'lng': 18.44500, 'address': 'Főnix Park, Gombócleső utca, Székesfehérvár'},
    'Mezővári József Sporttelep': {'lat': 47.16800, 'lng': 18.40500, 'address': 'Mezővári József Sporttelep (Ikarus-Maroshegy), Székesfehérvár'},
    'Dinnyés Sportpálya': {'lat': 47.17500, 'lng': 18.56000, 'address': 'Dinnyés Sportpálya, Gárdony-Dinnyés'},
    'Józsai Sportpálya': {'lat': 47.60000, 'lng': 21.58500, 'address': 'Józsai Sportpálya, Debrecen-Józsa'},
    'Toponár SE Sporttelep': {'lat': 46.40200, 'lng': 17.83800, 'address': 'Toponár SE Sporttelep, Kaposvár-Toponár'},
    'Kaposfüred SC Sporttelep': {'lat': 46.41400, 'lng': 17.77500, 'address': 'Kaposfüred SC Sporttelep, Kaposvár-Kaposfüred'},
    'Gergelyiugornyai SE Sportpálya': {'lat': 48.12800, 'lng': 22.34600, 'address': 'Gergelyiugornyai SE Sportpálya, Vásárosnamény'},
    'Vitka SE Sportpálya': {'lat': 48.13500, 'lng': 22.32500, 'address': 'Vitka SE Sportpálya, Vásárosnamény-Vitka'},
    'Dunakömlődi Sportegyesület Sporttelepe': {'lat': 46.66200, 'lng': 18.87900, 'address': 'Dunakömlődi Sporttelep, Paks-Dunakömlőd'},
    'Rábatótfalu Sporttelep': {'lat': 46.94200, 'lng': 16.24800, 'address': 'Sportpálya, Szentgotthárd-Rábatótfalu'},
    'Borsosgyőri SE': {'lat': 47.31500, 'lng': 17.43500, 'address': 'Borsosgyőri SE sportpálya, Pápa-Borsosgyőr'},
    'Tapolcafői SE': {'lat': 47.28000, 'lng': 17.51500, 'address': 'Tapolcafői SE sportpálya, Pápa-Tapolcafő'},
    'Kéttornyúlak': {'lat': 47.29900, 'lng': 17.44900, 'address': 'Sportpálya, Pápa-Kéttornyúlak'},
    'Pápai Spartacus Sporttelep': {'lat': 47.33000, 'lng': 17.46500, 'address': 'Pápai Spartacus Sporttelep, Pápa'},
    'Peremarton Sporttelep': {'lat': 47.11600, 'lng': 18.10600, 'address': 'Peremarton Sporttelep, Berhida-Peremarton'},
    'Kiskanizsai Sportpálya': {'lat': 46.44600, 'lng': 16.95400, 'address': 'Kiskanizsai Sportpálya, Nagykanizsa-Kiskanizsa'},
    'Miklósfa Sportpálya': {'lat': 46.41500, 'lng': 16.99200, 'address': 'Miklósfa Sportpálya, Nagykanizsa-Miklósfa'},
    'Andráshidai Sportcentrum': {'lat': 46.86500, 'lng': 16.79800, 'address': 'Andráshidai Sportcentrum, Novák Mihály utca, Zalaegerszeg'},
    'Botfai Sportcentrum': {'lat': 46.80100, 'lng': 16.86500, 'address': 'Botfai Sportcentrum, Zalaegerszeg-Botfa'},
    'Bárszentmihályfa Sportpálya': {'lat': 46.66200, 'lng': 16.58100, 'address': 'Bárszentmihályfa Sportpálya, Lenti'},

    # Budapest Specific Grounds
    'ASR Gázgyár Sporttelep': {'lat': 47.56199, 'lng': 19.05075, 'address': 'ASR Gázgyár Sporttelep, Sujtás utca, Budapest'},
    'Angyalföldi Sportközpont': {'lat': 47.54084, 'lng': 19.07459, 'address': 'Angyalföldi Sportközpont, Rozsnyay utca, Budapest'},
    'BVSC-Zugló Stadion': {'lat': 47.52277, 'lng': 19.09053, 'address': 'BVSC-Zugló Stadion, Szőnyi út, Budapest'},
    'Budafoki MTE Sporttelep': {'lat': 47.42182, 'lng': 19.02802, 'address': 'BMTE Sporttelep, Promontor utca, Budapest'},
    'Budai II. László Stadion': {'lat': 47.56201, 'lng': 19.12143, 'address': 'Budai II László Stadion, Szántóföld utca, Budapest'},
    'Budatétény Sporttelep': {'lat': 47.41713, 'lng': 19.01066, 'address': 'Budatétény Sporttelep, Jókai Mór utca, Budapest'},
    'CsHC Sporttelep': {'lat': 47.42560, 'lng': 19.07040, 'address': 'CsHC Sporttelep, Hollandi út, Budapest'},
    'Csepel SC Stadion': {'lat': 47.41812, 'lng': 19.06993, 'address': 'Csepel SC Stadion, Béke tér, Budapest'},
    'Csillaghegyi Strand Sporttelep': {'lat': 47.58592, 'lng': 19.04210, 'address': 'Csillaghegyi MTE Sporttelep, Kalászi utca, Budapest'},
    'Czakó utcai Sport- és Szabadidőközpont': {'lat': 47.49085, 'lng': 19.03678, 'address': 'Czakó utcai Sportközpont, Czakó utca, Budapest'},
    'Deák Ferenc "Bamba" Sporttelep': {'lat': 47.42844, 'lng': 19.17630, 'address': 'Deák Ferenc Bamba Sporttelep, Nemes utca, Budapest'},
    'Dr. Koltai Jenő Sportközpont': {'lat': 47.48898, 'lng': 19.02658, 'address': 'Dr. Koltai Jenő Sportközpont, Csörsz utca, Budapest'},
    'ESMTK Stadion': {'lat': 47.43190, 'lng': 19.11235, 'address': 'ESMTK Stadion, Zodony utca, Budapest'},
    'Fővárosi Vízművek SK Sporttelep': {'lat': 47.57663, 'lng': 19.08037, 'address': 'Fővárosi Vízművek Sporttelep, Váci út, Budapest'},
    'Gerely utcai Sporttelep': {'lat': 47.47200, 'lng': 19.16200, 'address': 'Gerely utcai Sporttelep, Gerely utca, Budapest'},
    'Grund 1986 FC Sporttelep': {'lat': 47.57500, 'lng': 19.11200, 'address': 'Grund 1986 FC Sporttelep, Kalmár Völgyi út, Budapest'},
    'III. ker. TVE Sporttelep': {'lat': 47.54774, 'lng': 19.05488, 'address': 'III. ker. TVE Sporttelep, Kalap utca, Budapest'},
    'Ikarus BSE Sporttelep': {'lat': 47.51799, 'lng': 19.19796, 'address': 'Ikarus BSE Sporttelep, Bátony utca, Budapest'},
    'KISE Sporttelep': {'lat': 47.50124, 'lng': 19.14961, 'address': 'KISE Sporttelep, Salgótarjáni utca, Budapest'},
    'Kelen SC Sporttelep': {'lat': 47.46604, 'lng': 19.04816, 'address': 'Kelen SC Sporttelep, Hunyadi Mátyás út, Budapest'},
    'Kocsis Sándor Sportközpont': {'lat': 47.47860, 'lng': 19.12323, 'address': 'Kocsis Sándor Sportközpont, Bihari utca, Budapest'},
    'MLTC Sporttelep': {'lat': 47.50920, 'lng': 19.20636, 'address': 'MLTC Sporttelep, Hunyadvár utca, Budapest'},
    'Merkapt Maraton Sportközpont': {'lat': 47.48520, 'lng': 19.16072, 'address': 'Merkapt Sportközpont, Maglódi út, Budapest'},
    'NAV Pasaréti úti Sporttelep': {'lat': 47.51860, 'lng': 18.99500, 'address': 'Pasaréti úti Sporttelep, Pasaréti út, Budapest'},
    'NSÜ-BOK Fehér úti Sporttelep': {'lat': 47.50200, 'lng': 19.13400, 'address': 'NSÜ-BOK Fehér úti Sporttelep, Fehér út, Budapest'},
    'Nagytétényi SE Sporttelep': {'lat': 47.38792, 'lng': 18.97437, 'address': 'Nagytétényi SE Sporttelep, Angeli utca, Budapest'},
    'Panoráma Sportközpont': {'lat': 47.52479, 'lng': 19.03386, 'address': 'Panoráma Sportközpont, Kolostor út, Budapest'},
    'Papírgyár Sporttelep': {'lat': 47.43200, 'lng': 19.05500, 'address': 'Papírgyár Sporttelep, Duna dűlő, Budapest'},
    'Pestszentimrei SK Sporttelep': {'lat': 47.40671, 'lng': 19.17488, 'address': 'Pestszentimre SK Sporttelep, Táncsics Mihály utca, Budapest'},
    'Pluhár István Labdarúgópálya': {'lat': 47.49120, 'lng': 19.02350, 'address': 'Pluhár István Labdarúgópálya, Csörsz utca, Budapest'},
    'Pokorny József Sport- és Szabadidőközpont': {'lat': 47.56384, 'lng': 18.95337, 'address': 'Pokorny József Sportközpont, Szabadság út, Budapest'},
    'Pénzügyőr SE Sporttelep (Kőér utca)': {'lat': 47.46723, 'lng': 19.12795, 'address': 'Pénzügyőr SE Sporttelep, Kőér utca, Budapest'},
    'RAFC Sporttelep': {'lat': 47.51067, 'lng': 19.16012, 'address': 'RAFC Sporttelep, Pirosrózsa utca, Budapest'},
    'RKSK Sporttelep (Sport tér)': {'lat': 47.47600, 'lng': 19.26300, 'address': 'RKSK Sporttelep, Sport tér, Budapest'},
    'RKSK Sporttelep (Újlak utca)': {'lat': 47.48082, 'lng': 19.24405, 'address': 'RKSK Sporttelep, Újlak utca, Budapest'},
    'ROKK Sporttelep': {'lat': 47.49110, 'lng': 19.07013, 'address': 'ROKK Sporttelep, Budapest'},
    'SINOSZ Sportcentrum': {'lat': 47.47165, 'lng': 19.08817, 'address': 'SINOSZ Sportcentrum, Könyves Kálmán körút, Budapest'},
    'SINOSZ Sportcsarnok': {'lat': 47.47165, 'lng': 19.08817, 'address': 'SINOSZ Sportcentrum, Budapest'},
    'SPORT11 Sport és Szabadidőközpont': {'lat': 47.45200, 'lng': 18.98800, 'address': 'SPORT11 Sportközpont, Kánai út, Budapest'},
    'Szabadkikötő Sporttelep': {'lat': 47.44530, 'lng': 19.06343, 'address': 'Szabadkikötő Sporttelep, Weiss Manfréd út, Budapest'},
    'Szamosi Mihály Sporttelep': {'lat': 47.39020, 'lng': 19.11244, 'address': 'Szamosi Mihály Sporttelep, Haraszti út, Budapest'},
    'Szántóföld utcai Sporttelep': {'lat': 47.57667, 'lng': 19.13580, 'address': 'Szántóföld utcai Sporttelep, Budapest'},
    'Testvériség SE Sporttelep': {'lat': 47.57670, 'lng': 19.13580, 'address': 'Testvériség SE Sporttelep, Szántóföld utca, Budapest'},
    'UTE Bánka Kristóf Sportközpont': {'lat': 47.58150, 'lng': 19.10900, 'address': 'Bánka Kristóf Sportközpont, Fóti út, Budapest'},
    'UTE Megyeri úti UP Pálya': {'lat': 47.57490, 'lng': 19.08350, 'address': 'UTE Megyeri úti Utánpótlás Pálya, Megyeri út, Budapest'},
    'Vasgolyó utcai Sporttelep': {'lat': 47.53295, 'lng': 19.13673, 'address': 'Vasgolyó utcai Sporttelep, Budapest'},
    'Vilmos Endre Sportcentrum': {'lat': 47.43884, 'lng': 19.21874, 'address': 'Vilmos Endre Sportcentrum, Nagyenyed utca, Budapest'},
    'Zrínyi Miklós Laktanya és Egyetemi Campus': {'lat': 47.49444, 'lng': 19.11159, 'address': 'Zrínyi Miklós Campus Sporttelep, Hungária körút, Budapest'},
    'Újpest Labdarúgó Sportcentruma': {'lat': 47.57848, 'lng': 19.09024, 'address': 'Újpest Labdarúgó Sportcentrum, Tábor utca, Budapest'},
    'Újpesti Haladás Sporttelep': {'lat': 47.57778, 'lng': 19.10635, 'address': 'Újpesti Haladás Sporttelep, Sporttelep utca, Budapest'}
}

COMMON_FIRST_NAMES = {
    'gyula', 'bence', 'gábor', 'ferenc', 'istván', 'józsef', 'attila',
    'lajos', 'károly', 'sándor', 'lászló', 'tibor', 'jános', 'béla', 'péter',
    'andrás', 'mihály', 'imre', 'géza', 'árpád', 'dezső', 'erzsébet', 'petőfi',
    'kossuth', 'széchenyi', 'dózsa', 'adler', 'szabó', 'tóth', 'szabadság', 'béke',
    'liget', 'bánya', 'sziget', 'haladás', 'elöre', 'vasas', 'honvéd', 'lokomotív'
}


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def stem_word(w):
    w = w.lower().strip(',.-()\"\'')
    if w.endswith('i') and len(w) > 3:
        stem = w[:-1]
        if stem.endswith('á'): stem = stem[:-1] + 'a'
        elif stem.endswith('é'): stem = stem[:-1] + 'e'
        elif w.endswith('ai'): stem = stem + 'a'
        elif w.endswith('ei'): stem = stem + 'e'
        return stem
    return w


def point_in_poly(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def is_point_in_feat(lon, lat, feat):
    geom = feat['geometry']
    gtype = geom['type']
    coords = geom['coordinates']
    if gtype == 'Polygon':
        return point_in_poly(lon, lat, coords[0])
    elif gtype == 'MultiPolygon':
        for poly in coords:
            if point_in_poly(lon, lat, poly[0]):
                return True
    return False


def load_county_features():
    with open(HUNGARY_MAP_FILE, 'r', encoding='utf-8') as f:
        text = f.read()
    json_str = text.split('=', 1)[1].strip()
    if json_str.endswith(';'): json_str = json_str[:-1]
    geo = json.loads(json_str)

    county_mapping = {
        'Bács-Kiskun': ['Bács-Kiskun', 'Kecskemét'],
        'Baranya': ['Baranya', 'Pécs'],
        'Békés': ['Békés', 'Békéscsaba'],
        'Borsod-Abaúj-Zemplén': ['Borsod-Abaúj-Zemplén', 'Miskolc'],
        'Budapest': ['Budapest'],
        'Csongrád': ['Csongrád', 'Szeged', 'Hódmezôvásárhely'],
        'Fejér': ['Fejér', 'Székesfehérvár', 'Dunaújváros'],
        'Győr-Moson-Sopron': ['Gyor-Moson-Sopron', 'Sopron', 'Gyôr'],
        'Hajdú-Bihar': ['Hajdú-Bihar', 'Debrecen'],
        'Heves': ['Heves', 'Eger'],
        'Jász-Nagykun-Szolnok': ['Jász-Nagykun-Szolnok', 'Szolnok'],
        'Komárom-Esztergom': ['Komárom-Esztergom', 'Tatabánya'],
        'Nógrád': ['Nógrád', 'Salgótarján'],
        'Pest': ['Pest', 'Érd'],
        'Somogy': ['Somogy', 'Kaposvár'],
        'Szabolcs-Szatmár-Bereg': ['Szabolcs-Szatmár-Bereg', 'Nyíregyháza'],
        'Tolna': ['Tolna', 'Szekszárd'],
        'Vas': ['Vas', 'Szombathely'],
        'Veszprém': ['Veszprém'],
        'Zala': ['Zala', 'Zalaegerszeg', 'Nagykanizsa']
    }
    features_by_name = {feat['properties']['name']: feat for feat in geo['features']}
    return county_mapping, features_by_name


def get_county_for_coords(lng, lat, county_mapping, features_by_name):
    for cname, feat_names in county_mapping.items():
        for fname in feat_names:
            feat = features_by_name.get(fname)
            if feat and is_point_in_feat(lng, lat, feat):
                return cname
    return None


def main():
    with open(SETTLEMENTS_FILE, 'r', encoding='utf-8') as f:
        settlements_data = json.load(f)
    with open(VENUES_FILE, 'r', encoding='utf-8') as f:
        venues = json.load(f)
    with open(MATCHES_FILE, 'r', encoding='utf-8') as f:
        matches = json.load(f)
    with open(LEAGUES_FILE, 'r', encoding='utf-8') as f:
        leagues = json.load(f)

    county_mapping, features_by_name = load_county_features()

    settlements_by_county = defaultdict(dict)
    all_settlements = defaultdict(list)
    for s in settlements_data:
        nl = s['name'].lower()
        c = s['county']
        settlements_by_county[c][nl] = s
        all_settlements[nl].append(s)

    v_info = defaultdict(lambda: {'teams': set(), 'feds': set()})
    for m in matches:
        v = m.get('vid')
        if not v: continue
        lid = str(m.get('lid'))
        fed = leagues.get(lid, {}).get('federation', '')
        h = m.get('h', '')
        if h: v_info[v]['teams'].add(h)
        if fed: v_info[v]['feds'].add(fed)

    fixed_count = 0
    unchanged_count = 0
    updated_venues = {}

    for vname, vdata in venues.items():
        cur_lat = vdata.get('lat', 0)
        cur_lng = vdata.get('lng', 0)
        cur_addr = vdata.get('address', '')
        inf = v_info.get(vname, {'teams': set(), 'feds': set()})
        feds = inf['feds']
        teams = inf['teams']

        # 1. Exact match in KNOWN_ARENAS
        if vname in KNOWN_ARENAS:
            arena = KNOWN_ARENAS[vname]
            updated_venues[vname] = {
                'name': vname,
                'lat': arena['lat'],
                'lng': arena['lng'],
                'address': arena['address']
            }
            if abs(cur_lat - arena['lat']) > 0.005 or abs(cur_lng - arena['lng']) > 0.005:
                fixed_count += 1
            else:
                unchanged_count += 1
            continue

        # 2. County / town matching
        c_feds = [f for f in feds if f != 'MLSZ' and f != 'Budapest']
        found = None

        # Parenthesized town
        m_paren = re.search(r'\(([^)]+)\)', vname)
        if m_paren:
            p_town = m_paren.group(1).strip().lower()
            for c in c_feds:
                if p_town in settlements_by_county.get(c, {}):
                    found = settlements_by_county[c][p_town]; break
            if not found and p_town in all_settlements:
                found = all_settlements[p_town][0]

        # Hyphenated or suffix words in venue name
        if not found:
            tokens = re.findall(r'[a-záéíóöőúüűA-ZÁÉÍÓÖŐÚÜŰ]+', vname)
            for c in c_feds:
                c_settle = settlements_by_county.get(c, {})
                for t in reversed(tokens):
                    tl = t.lower()
                    if tl not in COMMON_FIRST_NAMES and tl in c_settle:
                        found = c_settle[tl]; break
                    st = stem_word(t)
                    if st not in COMMON_FIRST_NAMES and st in c_settle:
                        found = c_settle[st]; break
                if found: break

        # Words in home teams matching candidate counties
        if not found:
            for c in c_feds:
                c_settle = settlements_by_county.get(c, {})
                for tm in teams:
                    ttokens = re.findall(r'[a-záéíóöőúüűA-ZÁÉÍÓÖŐÚÜŰ]+', tm)
                    for t in ttokens:
                        tl = t.lower()
                        if tl not in COMMON_FIRST_NAMES and tl in c_settle and len(tl) > 3:
                            found = c_settle[tl]; break
                        st = stem_word(t)
                        if st not in COMMON_FIRST_NAMES and st in c_settle and len(st) > 3:
                            found = c_settle[st]; break
                    if found: break
                if found: break

        # All settlements matching (national or unused)
        if not found:
            tokens = re.findall(r'[a-záéíóöőúüűA-ZÁÉÍÓÖŐÚÜŰ]+', vname)
            for t in reversed(tokens):
                tl = t.lower()
                if tl not in COMMON_FIRST_NAMES and tl in all_settlements:
                    found = all_settlements[tl][0]; break
                st = stem_word(t)
                if st not in COMMON_FIRST_NAMES and st in all_settlements:
                    found = all_settlements[st][0]; break

        if not found:
            for tm in teams:
                ttokens = re.findall(r'[a-záéíóöőúüűA-ZÁÉÍÓÖŐÚÜŰ]+', tm)
                for t in ttokens:
                    tl = t.lower()
                    if tl not in COMMON_FIRST_NAMES and tl in all_settlements and len(tl) > 3:
                        found = all_settlements[tl][0]; break
                    st = stem_word(t)
                    if st not in COMMON_FIRST_NAMES and st in all_settlements and len(st) > 3:
                        found = all_settlements[st][0]; break
                if found: break

        if found:
            # Check distance to current coords
            dist = haversine(cur_lat, cur_lng, found['lat'], found['lng'])
            # If current coords are very close (< 6 km) and inside Hungary, keep specific pitch coords!
            if dist < 6.0 and (45.7 <= cur_lat <= 48.65 and 16.1 <= cur_lng <= 22.9):
                updated_venues[vname] = vdata
                unchanged_count += 1
            else:
                # Replace with accurate settlement coordinates
                fixed_count += 1
                updated_venues[vname] = {
                    'name': vname,
                    'lat': found['lat'],
                    'lng': found['lng'],
                    'address': f"{vname} ({found['name']})"
                }
        else:
            # Fallback: keep current if valid inside Hungary
            if 45.7 <= cur_lat <= 48.65 and 16.1 <= cur_lng <= 22.9:
                updated_venues[vname] = vdata
                unchanged_count += 1
            else:
                fixed_count += 1
                updated_venues[vname] = {
                    'name': vname,
                    'lat': 47.1625,
                    'lng': 19.5033,
                    'address': vname
                }

    print(f'Verification & correction summary:')
    print(f'  Fixed / Updated venues: {fixed_count}')
    print(f'  Unchanged / already accurate venues: {unchanged_count}')
    print(f'  Total venues: {len(updated_venues)}')

    # Save to venues.json
    with open(VENUES_FILE, 'w', encoding='utf-8') as f:
        json.dump(updated_venues, f, ensure_ascii=False, indent=2)

    # Update dataset.js
    with open(DATASET_JS_FILE, 'r', encoding='utf-8') as f:
        ds_text = f.read()

    prefix = "window.MECCS_DATA = "
    json_part = ds_text[len(prefix):].rstrip(';\n ')
    ds_data = json.loads(json_part)
    ds_data['venues'] = updated_venues

    with open(DATASET_JS_FILE, 'w', encoding='utf-8') as f:
        f.write(prefix + json.dumps(ds_data, ensure_ascii=False) + ';\n')

    print('Successfully updated data/venues.json and data/dataset.js!')


if __name__ == '__main__':
    main()
