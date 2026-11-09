"""Canvas chart with a clearly separated, time-aligned experimental forecast."""
import math
import pandas as pd
from engine import IST

def draw_forecast(canvas,history,forecast,title=''):
    canvas.delete('all');w=max(canvas.winfo_width(),600);h=max(canvas.winfo_height(),260)
    fg='#e4edf7';muted='#94a9c4';gold='#ffd166'
    canvas.create_text(16,12,anchor='nw',fill=fg,text=title,font=('Segoe UI',12,'bold'))
    if not forecast or forecast.get('error') or not history:
        canvas.create_text(16,48,anchor='nw',fill=muted,text=(forecast or {}).get('error','Select a forecast after Kronos completes. No synthetic prediction is substituted.'),width=w-40);return
    rows=history[-50:];future=forecast['median'];lo=forecast['low'];hi=forecast['high']
    if not future:return
    prices=[r[k] for r in rows for k in ('low','high')]+lo+hi
    if not all(math.isfinite(float(x)) for x in prices):return
    low=min(prices);high=max(prices);span=max(high-low,.01);low-=span*.08;high+=span*.08
    left,right,top,bottom=55,w-25,53,h-70;total=len(rows)+len(future)
    step=(right-left)/max(total,1)
    x=lambda i:left+(i+.5)*step
    y=lambda price:bottom-(price-low)/(high-low)*(bottom-top)
    for j in range(5):
        price=low+(high-low)*j/4;yy=y(price)
        canvas.create_line(left,yy,right,yy,fill='#26344a');canvas.create_text(left-5,yy,anchor='e',text=f'{price:.1f}',fill=muted)
    for i,r in enumerate(rows):
        color='#5de0b5' if r['close']>=r['open'] else '#ff8f9c'
        canvas.create_line(x(i),y(r['high']),x(i),y(r['low']),fill=color)
        half=max(1,min(4,step*.3));yt=y(max(r['open'],r['close']));yb=max(yt+1,y(min(r['open'],r['close'])))
        canvas.create_rectangle(x(i)-half,yt,x(i)+half,yb,fill=color,outline=color)
    n=len(rows);boundary=left+n*step
    canvas.create_line(boundary,top,boundary,bottom,fill=gold,dash=(5,4))
    canvas.create_text(boundary+6,top,anchor='nw',text='FORECAST',fill=gold)
    # Start band/path at last observed close to make the separation explicit.
    points=[(x(n-1),y(rows[-1]['close']))]+[(x(n+i),y(v)) for i,v in enumerate(hi)]
    points +=[(x(n+i),y(lo[i])) for i in range(len(lo)-1,-1,-1)]
    canvas.create_polygon(*[v for p in points for v in p],fill='#294967',outline='')
    line=[x(n-1),y(rows[-1]['close'])]
    for i,v in enumerate(future):line.extend([x(n+i),y(v)])
    canvas.create_line(*line,fill=gold,width=2)
    for label,key in (('K1','kronos_t1'),('K2','kronos_t2')):
        price=forecast.get(key)
        if price is not None:
            yy=y(price);canvas.create_line(boundary,yy,right,yy,fill='#b9a2ff',dash=(3,3))
            canvas.create_text(right-3,yy+(-10 if label=='K1' else 10),anchor='e',text=f'{label} {price:.2f}',fill='#d4c5ff')
    for i in (0,len(rows)-1):
        t=pd.Timestamp(rows[i]['time']).tz_convert(IST)
        canvas.create_text(x(i),bottom+16,text=t.strftime('%H:%M'),fill=muted)
    for i in (len(future)-1,):
        canvas.create_text(x(n+i),bottom+16,text=pd.Timestamp(forecast['timestamps'][i]).strftime('%H:%M'),fill=gold)
    canvas.create_text(left,h-31,anchor='nw',text='IST • Candles: observed   |   Gold: median forecast   |   Blue: sample min/max, NOT confidence',fill=muted)
