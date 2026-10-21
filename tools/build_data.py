# 從 OpenStreetMap 全台資料（Geofabrik）抽出餐廳、咖啡店，切成 0.1 度的小區塊給 App 直接讀
# 也找出百貨公司、大賣場的範圍，標記哪些店開在裡面
import json, math, os, re, sys, collections, datetime
import osmium

PBF = sys.argv[1]
OUT = sys.argv[2]
AMENITY = {'restaurant', 'fast_food', 'food_court', 'cafe', 'ice_cream'}
MALL_SHOP = {'mall', 'department_store'}
# 大賣場在地圖上常標成超市或量販，用店名認
BIG_STORE = re.compile(r'家樂福|大潤發|愛買|好市多|costco|ikea|宜家|大全聯|lopia|carrefour', re.I)
GRID = 0.01   # 百貨範圍的索引格子大小（約 1 公里）


def is_mall(t):
    shop = t.get('shop', '')
    if shop in MALL_SHOP:
        return True
    if shop in ('supermarket', 'wholesale', 'hypermarket', 'furniture') and BIG_STORE.search(t.get('name', '')):
        return True
    return False


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.shops = []
        self.malls = []   # (名稱, [外框座標...], (minlat, minlon, maxlat, maxlon))

    def add(self, kind, oid, t, lat, lon, year):
        name = t.get('name')
        if not name or t.get('amenity') not in AMENITY:
            return
        # 已標示結束營業的不收
        if t.get('end_date') or t.get('opening_hours', '').strip().lower() in ('closed', 'off'):
            return
        addr = ''.join(x for x in [t.get('addr:city', ''), t.get('addr:district', ''), t.get('addr:street', ''),
                                    (t.get('addr:housenumber') + '號') if t.get('addr:housenumber') else ''] if x)
        veg = 1 if (t.get('diet:vegetarian') in ('yes', 'only') or t.get('diet:vegan') in ('yes', 'only')) else 0
        self.shops.append({'id': kind + str(oid), 'name': name, 'lat': lat, 'lon': lon, 'year': year, 'veg': veg,
                           'addr': addr, 't': {k: t.get(k, '') for k in ('amenity', 'cuisine', 'opening_hours', 'phone', 'contact:phone', 'website', 'contact:website')}})

    def node(self, n):
        if 'amenity' in n.tags and 'name' in n.tags:
            self.add('n', n.id, dict(n.tags), n.location.lat, n.location.lon, n.timestamp.year)

    def way(self, w):
        if 'amenity' not in w.tags or 'name' not in w.tags:
            return
        try:
            pts = [(nd.lat, nd.lon) for nd in w.nodes if nd.location.valid()]
        except osmium.InvalidLocationError:
            return
        if pts:
            self.add('w', w.id, dict(w.tags), sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), w.timestamp.year)

    def area(self, a):
        t = dict(a.tags)
        if not t.get('name') or not is_mall(t):
            return
        try:
            for ring in a.outer_rings():
                pts = [(nd.lat, nd.lon) for nd in ring]
                if len(pts) < 3:
                    continue
                lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
                self.malls.append((t['name'], pts, (min(lats), min(lons), max(lats), max(lons))))
        except osmium.InvalidLocationError:
            pass


def inside(lat, lon, pts):
    c = False
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]; yj, xj = pts[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


h = H()
h.apply_file(PBF, locations=True, idx='flex_mem')

# 百貨範圍按格子建索引，再看每家店落在哪間裡面
grid = collections.defaultdict(list)
for m in h.malls:
    s, w, n, e = m[2]
    for y in range(math.floor(s / GRID), math.floor(n / GRID) + 1):
        for x in range(math.floor(w / GRID), math.floor(e / GRID) + 1):
            grid[(y, x)].append(m)

tiles = collections.defaultdict(list)
in_mall = 0
for sh in h.shops:
    lat, lon, t = sh['lat'], sh['lon'], sh['t']
    mall = ''
    for name, pts, (s, w, n, e) in grid.get((math.floor(lat / GRID), math.floor(lon / GRID)), []):
        if s <= lat <= n and w <= lon <= e and inside(lat, lon, pts):
            mall = name
            break
    if mall:
        in_mall += 1
    # v3：第 5 欄是資料最後更新年份，第 6 欄是所在的百貨／大賣場
    row = [sh['id'], sh['name'], round(lat, 5), round(lon, 5), sh['year'], mall, t['amenity'], t['cuisine'],
           t['opening_hours'], sh['addr'], t['phone'] or t['contact:phone'], t['website'] or t['contact:website'], sh['veg']]
    while row and row[-1] in ('', 0):
        row.pop()
    tiles[f'{math.floor(lat * 10)}_{math.floor(lon * 10)}'].append(row)

os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.json'):
        os.remove(os.path.join(OUT, f))
for key, rows in tiles.items():
    rows.sort(key=lambda r: r[0])
    with open(os.path.join(OUT, key + '.json'), 'w', encoding='utf-8') as fp:
        json.dump(rows, fp, ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as fp:
    json.dump({'v': 3, 'updated': datetime.date.today().isoformat(), 'count': len(h.shops), 'tiles': sorted(tiles)}, fp, separators=(',', ':'))
print('shops', len(h.shops), 'malls', len(h.malls), 'in malls', in_mall, 'tiles', len(tiles))
