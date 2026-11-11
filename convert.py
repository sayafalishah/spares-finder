"""Builds data.json for Spares Finder from the SAP export (.xlsx or .csv) in this repository."""
import csv, datetime, glob, io, json, os, re, subprocess, sys, time

DROP = []  # columns to leave out of the app, e.g. ['Rate', 'Last PO No']


def last_change(path):
    try:
        out = subprocess.run(['git', 'log', '-1', '--format=%ct', '--', path],
                             capture_output=True, text=True).stdout.strip()
        if out:
            return int(out)
    except Exception:
        pass
    return int(os.path.getmtime(path))


files = [f for f in glob.glob('*.xlsx') + glob.glob('*.csv') if not f.startswith('~$')]
if not files:
    sys.exit('Upload the SAP export (.xlsx or .csv) to the repository.')
path = max(files, key=last_change)


def cell(v):
    if v is None:
        return ''
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime('%d-%m-%Y')
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(round(v, 4))
    return str(v).strip()


if path.lower().endswith('.xlsx'):
    try:
        import openpyxl
    except ImportError:
        sys.exit('openpyxl is missing. Add "pip install openpyxl" to the workflow.')
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    table = [[cell(v) for v in row] for row in wb.worksheets[0].iter_rows(values_only=True)]
else:
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    first = text.split('\n', 1)[0]
    delim = '\t' if first.count('\t') > first.count(',') else ','
    table = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text, newline=''), delimiter=delim)]

table = [r for r in table if any(c for c in r)]
hi = next((i for i, r in enumerate(table[:15]) if any(re.search(r'material', c, re.I) for c in r)), 0)
headers = [h.strip() for h in table[hi]]


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
for r in table[hi + 1:]:
    r = r + [''] * len(headers)
    rows.append([r[i] for i in keep])

data = {'headers': [headers[i] for i in keep], 'rows': rows, 'map': m,
        'ts': int(time.time() * 1000), 'name': os.path.basename(path)}
with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
print('Wrote data.json:', len(rows), 'items from', path, m)
