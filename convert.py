"""Builds data.json for Spares Finder from the SAP CSV export in this repository."""
import csv, glob, io, json, os, re, sys, time

DROP = []  # columns to leave out of the app, e.g. ['Rate', 'Last PO No']

path = 'Instrument_Inventory.csv'
if not os.path.exists(path):
    found = sorted(glob.glob('*.csv'))
    if len(found) != 1:
        sys.exit('Keep exactly one CSV file in the repository.')
    path = found[0]

raw = open(path, 'rb').read()
for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
    try:
        text = raw.decode(enc)
        break
    except UnicodeDecodeError:
        pass

first = text.split('\n', 1)[0]
delim = '\t' if first.count('\t') > first.count(',') else ','
table = [r for r in csv.reader(io.StringIO(text, newline=''), delimiter=delim)]
headers = [h.strip() for h in table[0]]


def find(*patterns):
    for p in patterns:
        for i, h in enumerate(headers):
            if re.search(p, h, re.I):
                return i
    return -1


m = {
    'code': find(r'^material\s*code$', r'material.*(code|no)', r'^material$'),
    'desc': find(r'^description$', r'descr'),
    'loc': find(r'bin|rack|shelf'),
    'sloc': find(r'storage'),
    'qty': find(r'unrestricted', r'qty|quant|stock'),
    'unit': find(r'base unit', r'unit|uom'),
}
if m['code'] < 0:
    sys.exit('No Material Code column found. Columns are: ' + ', '.join(headers))

keep = [i for i, h in enumerate(headers) if h not in DROP]
new = {old: n for n, old in enumerate(keep)}
m = {k: new.get(v, -1) for k, v in m.items()}
rows = []
for r in table[1:]:
    if not any(c.strip() for c in r):
        continue
    r = [c.strip() for c in r] + [''] * len(headers)
    rows.append([r[i] for i in keep])

data = {'headers': [headers[i] for i in keep], 'rows': rows, 'map': m,
        'ts': int(time.time() * 1000), 'name': os.path.basename(path)}
with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
print('Wrote data.json:', len(rows), 'items from', path, m)
