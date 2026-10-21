# 從 OpenStreetMap 全台資料（Geofabrik）抽出餐廳、咖啡店，切成 0.1 度的小區塊給 App 直接讀
import json, math, os, sys, collections, datetime
import osmium

PBF = sys.argv[1]
OUT = sys.argv[2]
AMENITY = {'restaurant', 'fast_food', 'food_court', 'cafe', 'ice_cream'}


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.tiles = collections.defaultdict(list)
        self.n = 0

    def add(self, kind, oid, t, lat, lon):
        name = t.get('name')
        if not name or t.get('amenity') not in AMENITY:
            return
        addr = ''.join(x for x in [t.get('addr:city', ''), t.get('addr:district', ''), t.get('addr:street', ''),
                                    (t.get('addr:housenumber') + '號') if t.get('addr:housenumber') else ''] if x)
        veg = 1 if (t.get('diet:vegetarian') in ('yes', 'only') or t.get('diet:vegan') in ('yes', 'only')) else 0
        row = [kind + str(oid), name, round(lat, 5), round(lon, 5), t.get('amenity'), t.get('cuisine', ''),
               t.get('opening_hours', ''), addr, t.get('phone') or t.get('contact:phone', ''),
               t.get('website') or t.get('contact:website', ''), veg]
        while row and row[-1] in ('', 0):
            row.pop()
        key = f'{math.floor(lat * 10)}_{math.floor(lon * 10)}'
        self.tiles[key].append(row)
        self.n += 1

    def node(self, n):
        if 'amenity' in n.tags and 'name' in n.tags:
            self.add('n', n.id, dict(n.tags), n.location.lat, n.location.lon)

    def way(self, w):
        if 'amenity' not in w.tags or 'name' not in w.tags:
            return
        try:
            pts = [(nd.lat, nd.lon) for nd in w.nodes if nd.location.valid()]
        except osmium.InvalidLocationError:
            return
        if pts:
            self.add('w', w.id, dict(w.tags), sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


h = H()
h.apply_file(PBF, locations=True, idx='flex_mem')
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.json'):
        os.remove(os.path.join(OUT, f))
for key, rows in h.tiles.items():
    rows.sort(key=lambda r: r[0])
    with open(os.path.join(OUT, key + '.json'), 'w', encoding='utf-8') as fp:
        json.dump(rows, fp, ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as fp:
    json.dump({'updated': datetime.date.today().isoformat(), 'count': h.n, 'tiles': sorted(h.tiles)}, fp, separators=(',', ':'))
print('shops', h.n, 'tiles', len(h.tiles))
