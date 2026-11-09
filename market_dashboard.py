"""Measured sector-index performance and coverage-aware market bias."""
from screening import fresh
SECTORS={'NIFTYAUTO':'Auto','NIFTYIT':'IT','NIFTYPHARMA':'Pharma','NIFTYFMCG':'FMCG','NIFTYMETAL':'Metal','NIFTYREALTY':'Realty','NIFTYENERGY':'Energy','NIFTYPSUBANK':'PSU Banks','NIFTYPVTBANK':'Private Banks','NIFTYMEDIA':'Media','NIFTYHEALTHCARE':'Healthcare','NIFTYOILANDGAS':'Oil & Gas'}

def summary(rows,expected=0,now=None):
 rows=list(rows);stocks=[r for r in rows if r['kind']=='stock' and fresh(r,now)];sectors=[r for r in rows if r.get('sector') and fresh(r,now)]
 count=len(stocks);coverage=count/expected if expected else 0
 up=sum((r.get('session_change') or 0)>0 for r in stocks);down=sum((r.get('session_change') or 0)<0 for r in stocks)
 breadth=up/count if count else None
 indices=[r for r in rows if r['kind']=='index' and fresh(r,now)]
 nifty=next((r for r in indices if r['symbol'].replace('DEMO ','') in ('NIFTY','NIFTY 50')),None)
 bias='WAIT / INCOMPLETE';why='Need >=80% fresh universe coverage, NIFTY and >=3 sector indices'
 if coverage>=.8 and nifty and len(sectors)>=3:
  pos=sum((r.get('session_change') or 0)>0 for r in sectors)/len(sectors)
  ht=nifty.get('htf',{})
  if breadth>=.6 and pos>=.6 and ht.get('30')==ht.get('60')=='BULL':bias='BULLISH';why='Breadth + sector strength + NIFTY 30/60m agree'
  elif breadth<=.4 and pos<=.4 and ht.get('30')==ht.get('60')=='BEAR':bias='BEARISH';why='Weak breadth + sectors + NIFTY 30/60m agree'
  else:bias='MIXED / SELECTIVE';why='Market evidence is not aligned'
 return dict(bias=bias,why=why,coverage=coverage,count=count,expected=expected,up=up,down=down,breadth=breadth,
             sectors=sorted(sectors,key=lambda r:-(r.get('session_change') or 0)),indices=indices)


def draw_dashboard(c,data,ml_count=0):
 c.delete('all');w=max(c.winfo_width(),900);h=max(c.winfo_height(),520)
 text='#e4edf7';muted='#92a9c0';green='#4de0b6';red='#ff899a';blue='#73adff'
 c.create_text(24,20,anchor='nw',text='MARKET COMMAND CENTRE',fill=text,font=('Segoe UI',19,'bold'))
 c.create_text(24,53,anchor='nw',text='Session-open returns • Scanned F&O stocks • Fresh closed candles • Research signals',fill=muted,font=('Segoe UI',10))
 cards=[('MARKET BIAS',data['bias'],blue),('FRESH COVERAGE',f"{data['count']} / {data['expected']} stocks",green),('ADVANCE / DECLINE',f"{data['up']} / {data['down']}",green),('ML AGREEMENT',f'{ml_count} candidates',blue)]
 gap=14;cw=(w-48-gap*3)/4
 for i,(label,value,color) in enumerate(cards):
  x=24+i*(cw+gap);c.create_rectangle(x,85,x+cw,178,fill='#14253b',outline='#243b57')
  c.create_text(x+15,100,anchor='nw',text=label,fill=muted,font=('Segoe UI',9,'bold'))
  c.create_text(x+15,130,anchor='nw',text=value,fill=color,font=('Segoe UI',13,'bold'))
 c.create_text(24,195,anchor='nw',text=data['why'],fill=muted)
 c.create_text(24,232,anchor='nw',text='SECTOR STRENGTH',fill=text,font=('Segoe UI',13,'bold'))
 sectors=data['sectors'];tilew=(w-48-3*12)/4
 for i,r in enumerate(sectors[:12]):
  x=24+(i%4)*(tilew+12);y=265+(i//4)*82;change=r.get('session_change') or 0;positive=change>=0
  c.create_rectangle(x,y,x+tilew,y+70,fill='#14382f' if positive else '#3c2330',outline='')
  c.create_text(x+12,y+11,anchor='nw',text=r['sector'],fill=text,font=('Segoe UI',11,'bold'))
  c.create_text(x+12,y+36,anchor='nw',text=f'{change:+.2f}%  |  {r.get("bias","WAIT")}',fill=green if positive else red,font=('Segoe UI',12))
 if not sectors:c.create_text(24,270,anchor='nw',text='Waiting for sector-index data. No sector ranking is inferred from stock names.',fill=muted)
 y=265+max(1,(len(sectors[:12])+3)//4)*82+14
 indextext='   •   '.join(f"{r['symbol']}: {(r.get('session_change') or 0):+.2f}%" for r in data['indices'][:5])
 c.create_text(24,y,anchor='nw',text=indextext or 'Index data pending',fill=text,font=('Segoe UI',10))
 c.create_text(24,y+30,anchor='nw',text='ML: chronological validation required. SHAP explains model output, not causation. No orders are sent.',fill=muted)
 c.configure(scrollregion=(0,0,w,max(h,y+70)))
