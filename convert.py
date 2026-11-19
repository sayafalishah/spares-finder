"""Builds the data files for Spares Finder from the SAP exports (.xlsx or .csv) in this repository.

Every export in the main folder is read. Each row goes to an inventory by its material code prefix
(for example CC_GH_ = General Items). If the prefix is not listed, the file name decides
(a file called Electrical_Inventory.xlsx fills the Electrical inventory).
"""
import csv, datetime, hashlib, io, json, os, re, subprocess, sys, time
from urllib.parse import quote

DROP = []  # columns to leave out of the app, e.g. ['Rate', 'Last PO No']

# id, title, material code prefixes, file-name hints, output file
INVENTORIES = [
    ('instrument', 'Instrument Inventory', ['CC_INST_'], ['instrument'], 'data.json'),
    ('general', 'General Items', ['CC_GH_'], ['general', 'gh_'], 'data-general.json'),
    ('misc', 'Miscellaneous Items', ['CC_MISC_'], ['misc'], 'data-misc.json'),
    ('electrical', 'Electrical Inventory', ['CC_ELEC_'], ['electrical', 'elec'], 'data-electrical.json'),
    ('mechanical', 'Mechanical Inventory', ['CC_MECH_'], ['mechanical', 'mech'], 'data-mechanical.json'),
]


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



def norm(c):
    return re.sub(r'\s+', '', c).upper()


def find(headers, *patterns):
    for p in patterns:
        for i, h in enumerate(headers):
            if re.search(p, h, re.I):
                return i
    return -1


CODE_PATTERNS = (r'^material\s*code$', r'material.*(code|no)', r'^material$')

# ---- 1. read every SAP export in the main folder and sort its rows into inventories ----
files = sorted(f for f in os.listdir('.') if f.lower().endswith(('.xlsx', '.csv')) and not f.startswith('~$'))
if not files:
    sys.exit('Upload the SAP export (.xlsx or .csv) to the repository.')
groups = {inv[0]: [] for inv in INVENTORIES}
unassigned = []
for path in files:
    table = [r for r in read_table(path) if any(c for c in r)]
    if not table:
        continue
    hi = next((i for i, r in enumerate(table[:15]) if any(re.search(r'material', c, re.I) for c in r)), 0)
    headers = [h.strip() for h in table[hi]]
    ci = find(headers, *CODE_PATTERNS)
    if ci < 0:
        print('SKIPPED', path, '- no Material Code column. Columns are:', ', '.join(headers))
        continue
    fname = os.path.basename(path).lower()
    hint = next((i[0] for i in INVENTORIES if any(k in fname for k in i[3])), None)
    per = {}
    for r in table[hi + 1:]:
        r = (r + [''] * len(headers))[:len(headers)]
        code = norm(r[ci])
        if not code:
            continue
        inv = next((i[0] for i in INVENTORIES if any(code.startswith(p) for p in i[2])), hint)
        if inv is None:
            unassigned.append(code)
            continue
        per.setdefault(inv, []).append(r)
    for inv, rs in per.items():
        groups[inv].append((headers, rs, os.path.basename(path)))
    print(path, '->', {k: len(v) for k, v in per.items()})
if unassigned:
    print('WARNING:', len(unassigned), 'rows have a code that matches no inventory, for example', unassigned[:5])

# ---- optional extra search words: files in extra/ with a Material Code column and any other columns ----
extra = {}
specs = {}
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
            sc = [i for i in range(len(hh)) if i != ci and re.search(r'spec', hh[i], re.I)]
            words = [r[i].strip() for i in range(len(hh)) if i != ci and i not in sc and r[i].strip()]
            sw = [r[i].strip() for i in sc if r[i].strip()]
            if key and sw:
                sl = specs.setdefault(key, [])
                for w in sw:
                    if w not in sl:
                        sl.append(w)
            lst = extra.setdefault(key, []) if key and words else []
            for w in words:
                if w not in lst:
                    lst.append(w)
        print('Read additional descriptions from', fn)

# ---- 2. write one data file per inventory ----
for inv_id, title, _prefixes, _hints, out_file in INVENTORIES:
    parts = groups[inv_id]
    if not parts:
        print('No data yet for', title)
        continue
    hs = []
    for headers, _rs, _n in parts:
        for h in headers:
            if h and h not in hs and h not in DROP:
                hs.append(h)
    rows = []
    for headers, rs, _n in parts:
        idx = [headers.index(h) if h in headers else -1 for h in hs]
        rows += [[r[i] if i >= 0 else '' for i in idx] for r in rs]
    m = {
        'code': find(hs, *CODE_PATTERNS),
        'desc': find(hs, r'^description$', r'descr'),
        'loc': find(hs, r'bin|rack|shelf'),
        'sloc': find(hs, r'storage'),
        'qty': find(hs, r'unrestricted', r'qty|quant|stock'),
        'unit': find(hs, r'base unit', r'unit|uom'),
    }
    for label, store, key in (('Additional Description', extra, 'extra'), ('Specifications', specs, 'spec')):
        vals = [' | '.join(store.get(norm(r[m['code']]), [])) for r in rows] if store else []
        if any(vals):
            hs.append(label)
            m[key] = len(hs) - 1
            for r, v in zip(rows, vals):
                r.append(v)
            print(title, '-', label, 'matched', sum(1 for v in vals if v), 'rows')
    data = {'headers': hs, 'rows': rows, 'map': m, 'id': inv_id, 'title': title,
            'name': ', '.join(sorted({n for _h, _r, n in parts}))}
    digest = hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    try:
        same = json.load(open(out_file, encoding='utf-8')).get('h') == digest
    except Exception:
        same = False
    if same:
        print(title, ': unchanged,', len(rows), 'rows')
        continue
    data['ts'] = int(time.time() * 1000)
    data['h'] = digest
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print('Wrote', out_file, ':', len(rows), 'rows for', title)

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
