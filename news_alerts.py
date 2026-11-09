"""Important-news classification; impact is a review hypothesis, not a price forecast."""
import hashlib
import pandas as pd
from engine import IST

def important(items,now=None):
 now=pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now);out=[]
 groups={'RBI / rates':('rbi','monetary policy','repo rate'), 'FED / rates':('federal reserve','fomc','fed meeting'), 'Earnings / results':('earnings','quarterly','financial results','net profit','revenue','guidance'), 'Budget / elections':('budget','election')}
 for item in items:
  n=item.get('newsObject',{});title=str(n.get('title',''));body=title+' '+str(n.get('text',''))
  try:
   t=pd.Timestamp(item['publishDate']);t=t.tz_localize(IST) if t.tzinfo is None else t
   if not 0<=(now-t).total_seconds()<=86400:continue
  except Exception:continue
  tags=[tag for tag,words in groups.items() if any(w in body.lower() for w in words)]
  if tags:
   impact='Review bank/rate-sensitive stock volatility' if any('rates' in t for t in tags) else 'Review company guidance, margins and sector peers' if 'Earnings / results' in tags else 'Broad-market event risk; review overnight exposure'
   out.append(dict(id=hashlib.sha256((title+str(t)).encode()).hexdigest(),title=title,symbol=item.get('smSymbol') or 'MACRO / UNMAPPED',tags=', '.join(tags),published=str(t),source=n.get('url') or n.get('newsUrl') or item.get('newsUrl') or 'Dhan licensed news feed (article URL not supplied)',impact=impact))
 return out
