"""Builds data.json for Spares Finder from the SAP export (.xlsx or .csv) in this repository."""
import csv, datetime, hashlib, io, json, os, re, subprocess, sys, time
from urllib.parse import quote

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


files = [f for f in os.listdir('.') if f.lower().endswith(('.xlsx', '.csv')) and not f.startswith('~$')]
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


def read_table(path):
    if path.lower().endswith('.xlsx'):
        try:
            import openpyxl
        except ImportError:
            sys.exit('openpyxl is missing. Add "pip install openpyxl" to the workflow.')
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        return [[cell(v) for v in row] for row in wb.worksheets[0].iter_rows(values_only=True)]
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    first = text.split('\n', 1)[0]
    delim = '\t' if first.count('\t') > first.count(',') else ','
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text, newline=''), delimiter=delim)]


table = read_table(path)

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

# ---- optional extra search words: files in extra/ with a Material Code column and any other columns ----
extra = {}
if os.path.isdir('extra'):
    for fn in sorted(os.listdir('extra')):
        if not fn.lower().endswith(('.xlsx', '.csv')) or fn.startswith('~$'):
            continue
        t = [r for r in read_table(os.path.join('extra', fn)) if any(c for c in r)]
        if not t:
            continue
        hh = [h.strip() for h in t[0]]
        ci = next((i for i, h in enumerate(hh) if re.search(r'material|code', h, re.I)), 0)
        for r in t[1:]:
            r = r + [''] * len(hh)
            key = re.sub(r'\s+', '', r[ci]).upper()
            words = [r[i].strip() for i in range(len(hh)) if i != ci and r[i].strip()]
            lst = extra.setdefault(key, []) if key and words else []
            for w in words:
                if w not in lst:
                    lst.append(w)
        print('Read additional descriptions from', fn)
out_headers = [headers[i] for i in keep]
if extra:
    out_headers.append('Additional Description')
    m['extra'] = len(out_headers) - 1
    for r in rows:
        r.append(' | '.join(extra.get(re.sub(r'\s+', '', r[m['code']]).upper(), [])))
    print('Additional descriptions matched', sum(1 for r in rows if r[-1]), 'rows')

data = {'headers': out_headers, 'rows': rows, 'map': m,
        'ts': int(time.time() * 1000), 'name': os.path.basename(path)}
with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
print('Wrote data.json:', len(rows), 'items from', path, m)

# ---- documents: files in docs/ named CODE__type.ext, e.g. CC_INST_01010010__datasheet.pdf ----
TYPES = {'photo', 'drawing', 'datasheet', 'manual'}
EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf')

# ---- pictures are shrunk automatically so phones store small files ----
MAX_PX = {'drawing': 2000, 'datasheet': 2000}  # longest side in pixels, per type
DEFAULT_PX = 1200                              # all other pictures (photos, nameplates)
MAX_KB = 400                                   # shrink any picture larger than this
DONE_FILE = os.path.join('docs', '_shrunk.json')
done = json.load(open(DONE_FILE)) if os.path.exists(DONE_FILE) else {}


def sha(path):
    return hashlib.sha1(open(path, 'rb').read()).hexdigest()


def shrink(path, typ):
    ext = os.path.splitext(path)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        return
    from PIL import Image, ImageOps
    limit = MAX_PX.get(typ, DEFAULT_PX)
    before = os.path.getsize(path)
    with Image.open(path) as src:
        src.load()
        im = ImageOps.exif_transpose(src).copy()
    w, h = im.size
    if max(w, h) <= limit and before <= MAX_KB * 1024:
        return
    if max(w, h) > limit:
        k = limit / max(w, h)
        im = im.resize((round(w * k), round(h * k)), Image.LANCZOS)
    if ext in ('.jpg', '.jpeg'):
        im.convert('RGB').save(path, 'JPEG', quality=80, optimize=True, progressive=True)
    elif ext == '.png':
        im.save(path, 'PNG', optimize=True)
    else:
        im.save(path, 'WEBP', quality=80)
    print('Shrunk', os.path.basename(path), round(before / 1024), 'KB ->', round(os.path.getsize(path) / 1024), 'KB')


docs = {}
if os.path.isdir('docs'):
    for fn in sorted(os.listdir('docs')):
        base, ext = os.path.splitext(fn)
        if ext.lower() not in EXTS:
            continue
        mt = re.match(r'^(.+?)__([A-Za-z]+)(?:[-_ ]?\d+)?$', base)
        code, typ = (mt.group(1), mt.group(2).lower()) if mt else (base, 'other')
        typ = typ if typ in TYPES else 'other'
        p = os.path.join('docs', fn)
        if ext.lower() == '.pdf':
            if os.path.getsize(p) > 5 * 1024 * 1024:
                print('WARNING: large PDF (', round(os.path.getsize(p) / 1048576, 1), 'MB ):', fn)
        elif done.get(fn) != sha(p):
            try:
                shrink(p, typ)
            except Exception as e:
                print('Could not shrink', fn, '-', e)
            done[fn] = sha(p)
        ver = hashlib.sha1(open(os.path.join('docs', fn), 'rb').read()).hexdigest()[:8]
        docs.setdefault(re.sub(r'\s+', '', code).upper(), []).append({'t': typ, 'f': 'docs/' + quote(fn) + '?v=' + ver})
if os.path.isdir('docs'):
    json.dump(done, open(DONE_FILE, 'w'), indent=0)
v = hashlib.sha1(json.dumps(docs, sort_keys=True).encode()).hexdigest()[:12]
with open('docs.json', 'w', encoding='utf-8') as f:
    json.dump({'v': v, 'files': docs}, f, separators=(',', ':'))
print('Wrote docs.json:', sum(len(x) for x in docs.values()), 'documents for', len(docs), 'codes')
