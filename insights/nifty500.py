"""Official current constituents, mapped to NSE cash by exact ISIN, never by name."""
import csv
import io
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from insights.config import IST

SOURCE = 'https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv'
MAX_BYTES = 512_000


def constituents(text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not {'Symbol', 'Series', 'ISIN Code', 'Company Name'}.issubset(reader.fieldnames or []):
        raise ValueError('NIFTY 500 constituent CSV header missing; an HTML error page is not a stock list')
    rows = []
    symbols, isins = set(), set()
    for raw in reader:
        symbol = (raw.get('Symbol') or '').strip().upper()
        isin = (raw.get('ISIN Code') or '').strip().upper()
        series=(raw.get('Series') or '').strip().upper()
        dummy=symbol.startswith('DUMMY') and bool(re.fullmatch(r'DUM[A-Z0-9]{9}',isin))
        if not symbol or (not re.fullmatch(r'IN[A-Z0-9]{10}', isin) and not dummy) or not series:
            raise ValueError('Invalid NIFTY 500 constituent row')
        if symbol in symbols or isin in isins:
            raise ValueError('Duplicate NIFTY 500 symbol or ISIN')
        symbols.add(symbol); isins.add(isin)
        rows.append(dict(ticker=symbol, isin=isin, company=raw['Company Name'].strip(), series=series, dummy=dummy))
    # Temporary extra securities can occur around corporate actions. Do not truncate them.
    if not 500 <= len(rows) <= 510:
        raise ValueError(f'Incomplete/unexpected NIFTY 500 list: {len(rows)} rows (expected 500–510)')
    return rows


def map_members(members, equities):
    by_isin = {}
    for item in equities:
        if item.get('kind') != 'stock' or item.get('segment') != 'NSE_EQ':
            continue
        isin = str(item.get('isin', '')).strip().upper()
        if isin and str(item.get('id', '')).isdigit():
            by_isin.setdefault(isin, {})[str(item['id'])] = item
    items, missing, ambiguous, excluded, ineligible = [], [], [], [], []
    used_ids = set()
    for member in members:
        if member.get('dummy') or member.get('series','EQ')!='EQ':
            ineligible.append(dict(symbol=member['ticker'],reason='NON-TRADABLE PLACEHOLDER' if member.get('dummy') else 'NON-EQ SERIES '+member['series'])); continue
        matches = list(by_isin.get(member['isin'], {}).values())
        if not matches:
            missing.append(member['ticker']); continue
        if len(matches) != 1 or matches[0]['id'] in used_ids:
            ambiguous.append(member['ticker']); continue
        item = matches[0]
        if str(item.get('asm_gsm_flag', '')).upper() == 'Y':
            excluded.append(member['ticker']); continue
        used_ids.add(item['id'])
        items.append(dict(item, ticker=member['ticker'], isin=member['isin'], universe='NIFTY 500'))
    return sorted(items, key=lambda x: x['ticker']), dict(
        constituents=len(members), mapped=len(items), missing_symbols=missing,
        ambiguous_symbols=ambiguous, surveillance_excluded=excluded, ineligible_constituents=ineligible)


class Nifty500Universe:
    def __init__(self, broker, root, fetch=None):
        self.broker = broker
        self.path = Path(root) / 'nifty500_constituents.json'
        self.fetch = fetch or self._download
        self._lock = threading.RLock()
        self._attempt = None
        self._error = None
        self._cached = None

    @staticmethod
    def _download():
        req = Request(SOURCE, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/csv'})
        with urlopen(req, timeout=15) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Constituent download exceeds size limit')
        return data.decode('utf-8-sig')

    def resolve(self, now):
        now = now.astimezone(IST)
        with self._lock:
            if self._cached is None:
                try:
                    cached = json.loads(self.path.read_text(encoding='utf-8'))
                    constituents(cached['csv'])
                    if cached['source'] != SOURCE: raise ValueError('Wrong cache source')
                    self._cached = cached
                except (OSError, ValueError, KeyError, TypeError):
                    self._cached = {}
            cached = self._cached
            try:
                stamp = datetime.fromisoformat(cached['retrieved_at'])
                age = (now-stamp).total_seconds()
            except (KeyError, TypeError, ValueError):
                stamp, age = None, float('inf')
            refresh = stamp is None or stamp.astimezone(IST).date() != now.date() or age < 0
            if refresh and (self._attempt is None or (now-self._attempt).total_seconds() >= 1800):
                self._attempt = now
                try:
                    override = os.getenv('INSIGHTS_NIFTY500_FILE', '').strip()
                    if override:
                        path = Path(override)
                        # A manual download is dated by its file time, not by each app restart.
                        stamp = datetime.fromtimestamp(path.stat().st_mtime, IST)
                        if path.stat().st_size > MAX_BYTES: raise ValueError('Constituent file too large')
                        text = path.read_text(encoding='utf-8-sig')
                    else:
                        text = self.fetch(); stamp = now
                    constituents(text)
                    age = (now-stamp).total_seconds()
                    if not 0 <= age <= 7*86400: raise ValueError('Constituent file is over 7 days old or future dated')
                    cached = dict(csv=text, retrieved_at=stamp.isoformat(), source=SOURCE,
                                  origin='MANUAL FILE — USER SUPPLIED' if override else 'OFFICIAL DOWNLOAD')
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = self.path.with_suffix('.tmp')
                    tmp.write_text(json.dumps(cached), encoding='utf-8'); os.replace(tmp, self.path)
                    self._cached = cached; self._error = None
                except Exception as exc:
                    self._error = str(exc)[:200]
            # Recompute from the accepted cache: failed downloads never renew its lifetime.
            try:
                age = (now-datetime.fromisoformat(cached['retrieved_at'])).total_seconds()
                if not 0 <= age <= 7*86400: raise ValueError('NIFTY 500 cache expired')
                members = constituents(cached['csv'])
            except (KeyError, ValueError, TypeError):
                raise ValueError('NIFTY 500 unavailable: '+(self._error or 'valid constituent list required')+
                                 '. Download the official CSV and set INSIGHTS_NIFTY500_FILE.') from None
            equities = (self.broker.nifty500_instruments(now) if hasattr(self.broker,'nifty500_instruments')
                        else self.broker.longterm_instruments())
            items, coverage = map_members(members, equities)
            if not items: raise ValueError('No NIFTY 500 ISINs mapped to the Dhan NSE equity master')
            coverage.update(name='NIFTY 500', source=SOURCE, retrieved_at=cached['retrieved_at'],
                            origin=cached.get('origin'), cache_age_days=round(age/86400,2),
                            status='CACHED — REFRESH FAILED' if self._error else 'CURRENT DOWNLOAD',
                            error=self._error)
            if coverage['origin'] == 'MANUAL FILE — USER SUPPLIED': coverage['status']='MANUAL FILE'
            return items, coverage
