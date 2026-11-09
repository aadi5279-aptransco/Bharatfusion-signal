"""Windows desktop research scanner. Start with python app.py."""
from __future__ import annotations
import csv,json,os,queue,threading,time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,filedialog,simpledialog
import pandas as pd
from engine import analyze,demo_frame,IST,bars
from data import Dhan,DataError,AuthError,Cache,universe
from kronos_adapter import Forecaster,ForecastError
from screening import top_momentum,assess_fundamentals,confirm,fresh
from forecast_queue import ForecastQueue
from forecast_chart import draw_forecast
from ml_engine import ModelService,train
from sentiment import SentimentService,risk_overlay,suggested_units
from market_dashboard import SECTORS,summary,draw_dashboard
from breakout import plan,previous_session
from timed_scans import plans,ranked,status as scan_status
from training_queue import AutoTraining
from strategy_service import StrategyService
from strategy_rules import empty
from market_safety import parse_ban,parse_delivery,event_gate
from paper_watch import PaperWatch
from news_alerts import important
from refresh_schedule import next_refresh
from compact_view import COLUMNS,HEADINGS,compact,details,STRATEGY_TABS,strategy_rows,all_strategy_rows
from discovery_rules import institutional,ai_selected
from rsi_strategy import scan as rsi_scan
from scanx_source import fetch as fetch_scanx

ROOT=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'BharatSignalFusion'
BG='#0b1220'; PANEL='#121e30'; TEXT='#e4edf7'; MUTED='#94a9c4'; GREEN='#5de0b5'

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('BharatSignal Fusion | Research Scanner 0.7.1'); self.geometry('1380x880'); self.minsize(1050,700); self.configure(bg=BG)
        self.events=queue.Queue(); self.stop=threading.Event(); self.worker=None; self.results={}; self.selected_symbol=None; self.closing=False; self.run_id=0; self.forecast_jobs=ForecastQueue(); self.forecasts={}; self.forecast_states={}; self.forecast_seen=set();self.expected_stocks=0;self.news_state={};self.news_jobs=queue.Queue(maxsize=1);self.training_worker=None;self.last_auto_train='';self.auto_training=AutoTraining(ROOT);self.strategy_selection=None;self.news_alerts=[];self.news_seen=set();self.paper_watch=PaperWatch(ROOT)
        style=ttk.Style(); style.theme_use('clam')
        style.configure('.',background=BG,foreground=TEXT,font=('Segoe UI',10))
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=30)
        style.configure('Treeview.Heading',background='#24344c',foreground=TEXT,font=('Segoe UI',10,'bold'))
        style.map('Treeview',background=[('selected','#244663')])
        style.configure('TButton',background='#244663',padding=7)
        for widget in ('TEntry','TCombobox','TSpinbox'):
            style.configure(widget,fieldbackground='#f1f5f9',foreground='#10243a',insertcolor='#10243a',selectbackground='#245a7c',selectforeground='white')
            style.map(widget,fieldbackground=[('readonly','#f1f5f9'),('disabled','#cbd5e1')],foreground=[('readonly','#10243a'),('disabled','#526477')])
        self.option_add('*TCombobox*Listbox.background','#f1f5f9')
        self.option_add('*TCombobox*Listbox.foreground','#10243a')
        self.option_add('*TCombobox*Listbox.selectBackground','#245a7c')
        self.option_add('*TCombobox*Listbox.selectForeground','white')
        style.configure('TNotebook.Tab',padding=(6,8),background=PANEL,font=('Segoe UI',9))
        style.map('TNotebook.Tab',background=[('selected','#244663')],foreground=[('selected',TEXT),('!selected',TEXT)])
        head=tk.Frame(self,bg=BG); head.pack(fill='x',padx=20,pady=(16,8))
        tk.Label(head,text='BHARATSIGNAL  /  FUSION',bg=BG,fg=TEXT,font=('Segoe UI',21,'bold')).pack(side='left')
        tk.Label(head,text='RESEARCH EDITION • NO ORDERS',bg=BG,fg=GREEN).pack(side='right')
        self.predictor_thread=threading.Thread(target=self.forecast_loop,daemon=True); self.predictor_thread.start()
        threading.Thread(target=self.news_loop,daemon=True).start()
        self.journal_jobs=queue.Queue(maxsize=200)
        threading.Thread(target=self.journal_loop,daemon=True).start()
        self.status=tk.StringVar(value='Ready • Demo data selected • Live integration requires local verification')
        tk.Label(self,textvariable=self.status,bg=PANEL,fg=GREEN,anchor='w',padx=14,pady=10).pack(fill='x',padx=20)
        controls=ttk.Frame(self); controls.pack(fill='x',padx=20,pady=10)
        self.mode=tk.StringVar(value='DEMO'); self.tf=tk.StringVar(value='3'); self.threshold=tk.IntVar(value=75)
        ttk.Label(controls,text='Source').pack(side='left'); ttk.Combobox(controls,textvariable=self.mode,values=['DEMO','DHAN LIVE'],state='readonly',width=12).pack(side='left',padx=5)
        ttk.Label(controls,text='Chart minutes').pack(side='left',padx=(12,3)); ttk.Combobox(controls,textvariable=self.tf,values=['3','5','15','60','240'],state='readonly',width=4).pack(side='left')
        ttk.Label(controls,text='Agreement threshold').pack(side='left',padx=(12,3)); ttk.Spinbox(controls,from_=60,to=95,textvariable=self.threshold,width=4).pack(side='left')
        self.startbutton=ttk.Button(controls,text='Connect / Start background',command=self.start); self.startbutton.pack(side='left',padx=10)
        ttk.Button(controls,text='Stop',command=self.stop_scan).pack(side='left')
        ttk.Button(controls,text='Export table',command=self.export).pack(side='right')
        auth=ttk.Frame(self); auth.pack(fill='x',padx=20,pady=(0,8))
        self.client=tk.StringVar(); self.token=tk.StringVar()
        ttk.Label(auth,text='Dhan client ID').pack(side='left'); ttk.Entry(auth,textvariable=self.client,width=18).pack(side='left',padx=5)
        ttk.Label(auth,text='Access token').pack(side='left'); ttk.Entry(auth,textvariable=self.token,show='•',width=45).pack(side='left',padx=5)
        ttk.Label(auth,text='Memory only • Dhan only').pack(side='left',padx=5)
        self.auto_kronos=tk.BooleanVar(value=True)
        ttk.Checkbutton(auth,text='Auto: top 20 + indices',variable=self.auto_kronos).pack(side='left',padx=5)
        ttk.Button(auth,text='Predict selected',command=self.predict_selected).pack(side='right')
        mlbar=ttk.Frame(self);mlbar.pack(fill='x',padx=20,pady=(0,8))
        self.ml_required=tk.BooleanVar(value=True);self.use_news=tk.BooleanVar(value=True);self.auto_tune=tk.BooleanVar(value=False)
        ttk.Checkbutton(mlbar,text='Require ML validation',variable=self.ml_required,command=self.refresh_decisions).pack(side='left')
        ttk.Checkbutton(mlbar,text='FinBERT news',variable=self.use_news).pack(side='left',padx=8)
        ttk.Checkbutton(mlbar,text='Retune after close',variable=self.auto_tune).pack(side='left')
        ttk.Button(mlbar,text='Train selected ML',command=self.train_selected).pack(side='left',padx=12)
        self.capital=tk.StringVar(value='100000');self.risk_pct=tk.StringVar(value='0.5')
        ttk.Label(mlbar,text='Paper capital ₹').pack(side='left');ttk.Entry(mlbar,textvariable=self.capital,width=10).pack(side='left')
        ttk.Label(mlbar,text='Risk %').pack(side='left',padx=(8,2));ttk.Entry(mlbar,textvariable=self.risk_pct,width=5).pack(side='left')
        auto_row=ttk.Frame(self);auto_row.pack(fill='x',padx=20,pady=(0,5))
        self.auto_ml=tk.BooleanVar(value=True)
        ttk.Checkbutton(auto_row,text='Auto train candidates + indices (3m ML)',variable=self.auto_ml).pack(side='left')
        ttk.Label(auto_row,text='Stock options: futures traps | BTST: 15:05 / 125D: 15:15 | Strategies are research; no orders').pack(side='left',padx=12)
        strategybar=ttk.Frame(self);strategybar.pack(fill='x',padx=20,pady=(0,5))
        self.strict_traps=tk.BooleanVar(value=False);self.delivery_proxy=tk.BooleanVar(value=False);self.show_blocked=tk.BooleanVar(value=False);self.time_only=tk.BooleanVar(value=False)
        ttk.Checkbutton(strategybar,text='Strict trap scanner',variable=self.strict_traps).pack(side='left')
        ttk.Checkbutton(strategybar,text='Allow prior-day delivery proxy',variable=self.delivery_proxy).pack(side='left',padx=5)
        ttk.Checkbutton(strategybar,text='Show all waiting rows',variable=self.show_blocked,command=self.render).pack(side='left',padx=5)
        ttk.Checkbutton(strategybar,text='125D time-only exit',variable=self.time_only).pack(side='left',padx=5)
        ttk.Button(strategybar,text='Import risk data',command=self.import_risk_data).pack(side='left',padx=5)
        ttk.Button(strategybar,text='Track selected (paper)',command=self.track_strategy).pack(side='left',padx=5)
        ttk.Button(strategybar,text='Paper positions',command=self.paper_positions).pack(side='left',padx=5)
        book=ttk.Notebook(self); self.book=book;book.pack(fill='both',expand=True,padx=20,pady=4)
        dash=ttk.Frame(book);book.add(dash,text='Dashboard')
        self.dashboard=tk.Canvas(dash,bg=BG,highlightthickness=0);ds=ttk.Scrollbar(dash,orient='vertical',command=self.dashboard.yview);self.dashboard.configure(yscrollcommand=ds.set)
        ds.pack(side='right',fill='y');self.dashboard.pack(fill='both',expand=True);self.dashboard.bind('<Configure>',lambda e:self.refresh_dashboard())
        intelligence=ttk.Frame(book);book.add(intelligence,text='AI / News / Risk')
        self.ai_text=tk.Text(intelligence,bg=PANEL,fg=TEXT,wrap='word',state='disabled',font=('Segoe UI',11))
        ai_scroll=ttk.Scrollbar(intelligence,orient='vertical',command=self.ai_text.yview);self.ai_text.configure(yscrollcommand=ai_scroll.set);ai_scroll.pack(side='right',fill='y');self.ai_text.pack(fill='both',expand=True)
        self.tables={};self.scan_labels={}
        self.columns=('symbol','plan_status','plan_direction','scan_release','daily_bias','weekly_bias','plan_entry','plan_stop','plan_t1','plan_t2','action','confirmation','kronos_t1','kronos_t2','ml_status','ml_probability','prior_date','prior_high','prior_low','plan_rvol','score','close','entry','stop','t1','t2','candle')
        self.strategy_columns=('symbol','strategy','strategy_status','option_side','atm_strike','expiry','premium_entry','premium_t1_est','premium_t2_est','premium_sl_est','quantity','estimated_risk','underlying_entry','underlying_t1','underlying_t2','underlying_sl','trigger_at','data_at','ban_check','delivery_pct','delivery_date','event_check','reason')
        self.table_columns={};self.strategy_lookup={}
        for name in ('Stock options','Intraday Top 10','BTST stocks','Institutional stocks','AI selected stocks','RSI strategy','Indices'):
            frame=ttk.Frame(book); book.add(frame,text=name)
            if name in STRATEGY_TABS+('Intraday Top 10',):
                label=ttk.Label(frame,text='Waiting for data. Unknown ban/delivery/events never pass. Turn on Show all waiting rows for diagnostics.',wraplength=1100)
                label.pack(fill='x',padx=8,pady=8);self.scan_labels[name]=label
                ttk.Label(frame,text=('Prices: option premium; targets/SL estimated. ' if name=='Stock options' else 'BTST CE rows: option premium estimates. 125D rows: cash prices. ' if name=='BTST stocks' else 'Prices: underlying research levels. ')+'Select a row for full reasons and checks.',wraplength=1100).pack(fill='x',padx=8,pady=(0,5))
            columns=COLUMNS
            self.table_columns[name]=columns
            tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse')
            for c in columns:
                tree.heading(c,text=HEADINGS[c])
                width=190 if c=='symbol' else 140 if c=='setup' else 110 if c=='contract' else 260 if c=='view_status' else 75
                tree.column(c,width=width,minwidth=65,stretch=c in ('symbol','view_status'),anchor='w' if c in ('symbol','setup','contract','view_status') else 'e')
            scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y')
            horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview);tree.configure(xscrollcommand=horizontal.set)
            horizontal.pack(side='bottom',fill='x');tree.pack(fill='both',expand=True)
            tree.tag_configure('buy',foreground=GREEN); tree.tag_configure('sell',foreground='#ff8f9c'); tree.tag_configure('wait',foreground=MUTED)
            tree.bind('<<TreeviewSelect>>',self.select); self.tables[name]=tree
        forecastframe=ttk.Frame(book); book.add(forecastframe,text='Kronos forecasts')
        fc=ttk.Frame(forecastframe);fc.pack(fill='x',pady=5)
        ttk.Label(fc,text='Predicted chart:').pack(side='left')
        self.forecast_symbol=tk.StringVar();self.forecast_picker=ttk.Combobox(fc,textvariable=self.forecast_symbol,state='readonly',width=28)
        self.forecast_picker.pack(side='left',padx=8);self.forecast_picker.bind('<<ComboboxSelected>>',lambda e:self.redraw_forecast())
        ttk.Button(fc,text='Forecast this instrument',command=self.predict_dropdown).pack(side='left',padx=5)
        self.forecast_progress=tk.StringVar(value='No forecasts yet • Auto forecasts up to 20 qualifying stocks plus all mapped indices')
        ttk.Label(fc,textvariable=self.forecast_progress).pack(side='left',padx=8)
        self.forecast_canvas=tk.Canvas(forecastframe,height=300,bg=PANEL,highlightthickness=0);self.forecast_canvas.pack(fill='both',expand=True)
        self.forecast_canvas.bind('<Configure>',lambda e:self.redraw_forecast())
        self.forecast_text=tk.Text(forecastframe,height=9,bg=PANEL,fg=TEXT,wrap='word',state='disabled',font=('Segoe UI',10))
        fs=ttk.Scrollbar(forecastframe,orient='vertical',command=self.forecast_text.yview);self.forecast_text.configure(yscrollcommand=fs.set)
        fs.pack(side='right',fill='y');self.forecast_text.pack(fill='both')
        logframe=ttk.Frame(book); book.add(logframe,text='Activity / Coverage')
        self.log=tk.Text(logframe,bg=PANEL,fg=TEXT,wrap='word',state='disabled'); self.log.pack(fill='both',expand=True)
        bottom=tk.Frame(self,bg=BG); bottom.pack(fill='both',padx=20,pady=10)
        self.canvas=tk.Canvas(bottom,height=190,bg=PANEL,highlightthickness=0); self.canvas.pack(side='left',fill='both',expand=True)
        self.detail=tk.Text(bottom,width=66,height=13,bg=PANEL,fg=TEXT,wrap='word',font=('Segoe UI',10),state='disabled'); self.detail.pack(side='right',fill='y',padx=(12,0))
        tk.Label(self,text='Agreement is not win probability. WAIT is valid. Index levels are underlying analysis, not option trade prices. No profit claims.',bg=BG,fg=MUTED).pack(pady=(0,12))
        self.render_pending=False;self.rendered_values={}
        self.book.bind('<<NotebookTabChanged>>',lambda e:self._render_now())
        self.book.enable_traversal()
        self.bind('<Control-Next>',lambda e:self.next_tab(1))
        self.bind('<Control-Prior>',lambda e:self.next_tab(-1))
        self.protocol('WM_DELETE_WINDOW',self.close); self.after(200,self.poll)
    def write_log(self,message):
        self.log.configure(state='normal'); self.log.insert('end',pd.Timestamp.now(tz=IST).strftime('%H:%M:%S')+'  '+message+'\n'); self.log.see('end'); self.log.configure(state='disabled')
    def next_tab(self,direction):
        tabs=self.book.tabs();index=tabs.index(self.book.select());self.book.select(tabs[(index+direction)%len(tabs)]);return 'break'
    def start(self):
        if self.worker and self.worker.is_alive(): return
        mode=self.mode.get()
        if mode=='DHAN LIVE' and (not self.client.get().strip() or not self.token.get().strip()):
            messagebox.showerror('Credentials required','Enter Dhan client ID and token here on your PC. Do not share them in chat.'); return
        try: threshold=int(self.threshold.get()); minutes=int(self.tf.get())
        except (ValueError,tk.TclError): messagebox.showerror('Settings','Enter a numeric threshold'); return
        if minutes not in (3,5,15,60,240):messagebox.showerror('Settings','Choose 3, 5, 15, 60 or 240 minutes');return
        if not 60<=threshold<=95: messagebox.showerror('Settings','Threshold must be 60–95'); return
        self.auto_training.clear();self.run_id+=1;self.selected_symbol=None;self.results.clear();self.forecasts.clear();self.forecast_states.clear();self.forecast_seen.clear();self.show_forecasts();self.forecast_jobs.clear();self.expected_stocks=0;self.news_state={}
        for t in self.tables.values(): t.delete(*t.get_children())
        self.stop.clear(); self.startbutton.configure(state='disabled')
        try:capital=float(self.capital.get());risk_pct=float(self.risk_pct.get())
        except ValueError:messagebox.showerror('Risk','Enter numeric capital and risk %');self.startbutton.configure(state='normal');return
        if not 0<capital or not 0<risk_pct<=2:messagebox.showerror('Risk','Capital must be positive; risk must be >0 and <=2%');self.startbutton.configure(state='normal');return
        config=dict(strict=self.strict_traps.get(),proxy=self.delivery_proxy.get(),capital=capital,risk_pct=risk_pct)
        self.worker=threading.Thread(target=self.scan,args=(mode,self.client.get().strip(),self.token.get().strip(),minutes,threshold,self.run_id,self.use_news.get(),config),daemon=True); self.worker.start()
    def stop_scan(self):
        self.stop.set(); self.auto_training.clear(); self.forecast_jobs.clear(); self.events.put(('reset','Scanner stopped; levels invalidated')); self.status.set('Stopping after current network request…')
    def scan(self,mode,client,token,minutes,threshold,run_id=0,use_news=False,strategy_config=None):
        cache=None;depth_stop=None
        try:
            cache=Cache(ROOT);ml=ModelService(ROOT);self.events.put(('log',f'{mode}: starting. Rule strategy is unvalidated; signals are research candidates.'))
            if mode=='DEMO':
                items=[dict(symbol='DEMO STOCK '+str(i),kind='stock') for i in range(1,31)]+[dict(symbol='DEMO '+name,kind='index') for name in ('NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY','SENSEX')]
                items += [dict(symbol='DEMO '+name,kind='sector',sector=sector) for name,sector in SECTORS.items()]
                self.events.put(('universe',30))
                for i,item in enumerate(items):
                    if self.stop.is_set(): break
                    f=demo_frame(i,days=65); now=f.index[-1].normalize()+pd.Timedelta(hours=14)
                    # Explicitly synthetic momentum/volume cases to exercise the new ranking UI.
                    if i%3!=0:
                        import numpy as np
                        mask=(f.index>=now-pd.Timedelta(minutes=30))&(f.index<now)
                        ramp=np.arange(mask.sum())*.8
                        for col in ('open','high','low','close'):f.loc[mask,col]+=ramp
                        vmask=(f.index>=now-pd.Timedelta(minutes=5))&(f.index<now)
                        f.loc[vmask,'volume']*=4
                    if item['kind']=='stock' and i%3!=0:
                        prior=previous_session(f,now)
                        price=prior['high']+.2 if i%2==0 else prior['low']-.2
                        last=(f.index>=now-pd.Timedelta(minutes=3))&(f.index<now)
                        f.loc[last,'open']=price;f.loc[last,'close']=price
                        f.loc[last,'high']=price+.1;f.loc[last,'low']=price-.1;f.loc[last,'volume']=300000
                    if item['kind']=='stock' and i%3!=0:
                        prior=previous_session(f,now);start=now.normalize()+pd.Timedelta(hours=9,minutes=15)
                        opening=(f.index>=start)&(f.index<start+pd.Timedelta(minutes=30))
                        values=prior['high']+.2+np.arange(opening.sum())*.01
                        f.loc[opening,'open']=values-.02;f.loc[opening,'close']=values
                        f.loc[opening,'high']=values+.05;f.loc[opening,'low']=values-.05;f.loc[opening,'volume']=300000
                    result=analyze(f,item['symbol'],item['kind'],minutes=minutes,now=now,threshold=threshold)
                    result.update(plans(f,now) if item['kind']=='stock' else plan(f,now,item['kind']));result['ml_minutes']=3
                    result['sector']=item.get('sector');result['ml']={'status':'DEMO / NOT TRAINED','pass_gate':False}
                    result['run_id']=run_id;result['fundamentals']=assess_fundamentals(None,item['kind']);result['minutes']=minutes; result['mode']='DEMO'; result['observed']=pd.Timestamp.now(tz=IST).isoformat(); self.events.put(('result',result))
                self.events.put(('forecast_batch',None))
                self.events.put(('status','DEMO • Synthetic historical candles • Not live • Select a row for analysis'))
                return
            api=Dhan(client,token,self.stop);strategy_service=StrategyService(api,cache,ROOT,self.stop,**(strategy_config or {}))
            self.events.put(('status','Downloading current Dhan master and mapping all eligible F&O stock underlyings…'))
            items=universe(); self.events.put(('log',f'Mapped {sum(x["kind"]=="stock" for x in items)} stocks and {sum(x["kind"]=="index" for x in items)} indices. Initial warm-up may take several minutes.'))
            self.events.put(('universe',sum(x['kind']=='stock' for x in items)))
            depth_stop=threading.Event();threading.Thread(target=self.depth_loop,args=(client,token,[x for x in items if x['kind']=='stock'],depth_stop,run_id),daemon=True).start()
            if use_news:threading.Thread(target=self.collect_news,args=(client,token,items,depth_stop,run_id),daemon=True).start()
            failures=0;company_cache={};news_last=0;backfilled=set()
            while not self.stop.is_set():
                started=time.monotonic();ok=0;errors=0;cycle=[]
                scanx={};scanx_status='ScanX unavailable'
                try:
                    scanx=fetch_scanx(pd.Timestamp.now(tz=IST));scanx_status=f'ScanX snapshot: {len(scanx)} candidates'
                    items=universe(extra_ids=scanx,reuse=True)
                    mapped={x['id'] for x in items if x['kind']=='stock'}
                    missing=set(scanx)-mapped
                    if missing:self.events.put(('log',f'ScanX: {len(missing)} candidates not eligible/mapped in Dhan NSE EQ master'))
                    self.events.put(('universe',sum(x['kind']=='stock' for x in items)))
                except Exception as exc:scanx_status='ScanX unavailable: '+str(exc)[:180]
                self.events.put(('log',scanx_status))
                self.events.put(('scanx_status',(run_id,scanx,scanx_status)))
                # Reset visible eligibility before each scan. No stale BUY rows survive a failed request.
                self.events.put(('reset','Refreshing: previous signals are no longer current'))
                for n,item in enumerate(items):
                    if self.stop.is_set(): break
                    symbol=item['symbol']; key=item['segment']+':'+item['id']
                    self.events.put(('status',f'DHAN scan {n+1}/{len(items)} • {symbol} • Success {ok} / Errors {errors}'))
                    try:
                        now=pd.Timestamp.now(tz=IST); old=cache.load(key)
                        start=now.normalize()-pd.Timedelta(days=89) if old is None or (key not in backfilled and len(old) and (now.normalize()-old.index[0]).days<75) else max(now.normalize()-pd.Timedelta(days=89),old.index[-1]-pd.Timedelta(minutes=5))
                        fresh=api.history(item,start,now);backfilled.add(key)
                        f=fresh if old is None else pd.concat([old,fresh])
                        f=f[~f.index.duplicated(keep='last')].sort_index()
                        f=f[f.index>=now.normalize()-pd.Timedelta(days=90)]
                        cache.save(key,fresh)
                        result=analyze(f,symbol,item['kind'],minutes,now,threshold)
                        result.update(plans(f,now) if item['kind']=='stock' else plan(f,now,item['kind']));result['ml_minutes']=3
                        result['sector']=item.get('sector');result['cache_key']=key
                        direction='LONG' if item['kind']=='stock' or result['bias']=='BULL' else 'SHORT'
                        result['ml']=ml.predict(bars(f,3,now),symbol,3,direction,cache.load_book(key))
                        result['run_id']=run_id;result['minutes']=minutes; result['mode']='DHAN LIVE'; result['observed']=now.isoformat()
                        snapshot=company_cache.get(symbol)
                        if item['kind']=='stock' and (result.get('timed_eligible') or result.get('intraday_plan',{}).get('timed_eligible') or top_momentum([result],now=now)):
                            if not snapshot or (now-pd.Timestamp(snapshot['fetched_at'])).total_seconds()>86400:
                                try:snapshot=api.company_info(item)
                                except DataError as exc:snapshot={'error':str(exc),'fetched_at':now.isoformat()}
                                company_cache[symbol]=snapshot
                        result['fundamentals']=assess_fundamentals(snapshot,item['kind'],now)
                        if item['kind']=='stock':
                            try:
                                opt,btst,daily,future=strategy_service.run(item,f,pd.Timestamp.now(tz=IST))
                                result.update(options_row=opt,btst_rows=btst)
                                for alert in self.paper_watch.monitor(item,f,daily,future,api,pd.Timestamp.now(tz=IST)):self.events.put(('alert',alert))
                            except Exception as exc:
                                result['options_row']=dict(empty('Trap scan','Strategy worker: '+str(exc)[:160]),symbol=symbol)
                                result['btst_rows']=[dict(empty(n,'Strategy worker: '+str(exc)[:160]),symbol=symbol) for n in ('125D breakout','BTST consolidation')]
                        if item['kind']=='stock':
                            current=pd.Timestamp.now(tz=IST)
                            for key,fn in (('institutional_row',lambda d:institutional(d,f,current,item['id'] in scanx and -300<=(current-pd.Timestamp(scanx[item['id']]['source_at'])).total_seconds()<=900,scanx_status)),('ai_row',lambda d:ai_selected(d,f,current,result.get('ml',{}))),('rsi_row',lambda d:rsi_scan(d,f,current))):
                                try:
                                    daily=strategy_service.daily(item,current,long_history=(key=='rsi_row' or (key=='institutional_row' and item['id'] in scanx))) if key in ('ai_row','rsi_row') or item['id'] in scanx else None
                                    prior_cash=f[f.index.normalize()<current.normalize()]
                                    if daily is not None and len(prior_cash) and daily.index[-1].normalize()<prior_cash.index[-1].normalize():raise ValueError('Daily history missing latest cash session')
                                    row=fn(daily)
                                    row.update(symbol=symbol,data_at=(f.index[-1]+pd.Timedelta(minutes=1)).isoformat(),source_at=scanx.get(item['id'],{}).get('source_at',''))
                                    if row.get('matched'):
                                        ticker=scanx.get(item['id'],{}).get('symbol') or item.get('ticker')
                                        if item.get('future'):
                                            gate=strategy_service.safety.gates(ticker or symbol,current)
                                            row['ban_check']=gate['ban_check'] if ticker else 'UNKNOWN / exchange ticker unavailable'
                                            if row['ban_check']!='PASS':row.update(eligible=False,reason=row['reason']+'; F&O ban check: '+row['ban_check'])
                                        else:row['ban_check']='N/A — cash stock outside mapped futures universe'
                                    if row.get('eligible'):
                                        age=(current-(f.index[-1]+pd.Timedelta(minutes=1))).total_seconds()
                                        risk=row['underlying_entry']-row['underlying_sl']
                                        live=float(f.close.iloc[-1])
                                        qty=max(0,min(10,int(strategy_service.budget/risk),int(strategy_service.capital/live)))
                                        row.update(quantity=qty,estimated_risk=qty*risk)
                                        if not 0<=age<=300 or live<=row['underlying_sl'] or live>=row['underlying_t1'] or abs(live-row['underlying_entry'])>.25*risk:row.update(eligible=False,reason=row['reason']+'; stale data or price moved beyond entry tolerance')
                                        if qty==0:row.update(eligible=False,reason=row['reason']+'; no quantity fits risk budget')
                                    result[key]=row
                                except Exception as exc:result[key]=dict(empty('Institutional RSI pullback' if key=='institutional_row' else 'RSI pullback + confirmation' if key=='rsi_row' else 'SMC cash setup','Analysis unavailable: '+str(exc)[:180]),symbol=symbol,data_at=current.isoformat())
                        cycle.append(result);self.events.put(('result',result));ok+=1;failures=0
                    except AuthError: raise
                    except (DataError,ValueError,KeyError,TypeError) as exc:
                        errors+=1; failures+=1; self.events.put(('log',symbol+': '+(str(exc) if isinstance(exc,DataError) else 'Invalid candle data; no signal')))
                        if failures>=8: raise DataError('8 consecutive failures: circuit breaker stopped scanning. Check access/network, then restart.')
                self.events.put(('retune_check',None))
                elapsed=round(time.monotonic()-started)
                next_deadline=next_refresh(started,time.monotonic())
                if elapsed>=300:self.events.put(('log',f'Refresh took {elapsed}s, exceeding five minutes; missed cycles skipped, no overlapping scan.'))
                self.events.put(('status',f'DHAN • Scan complete in {elapsed}s • {ok}/{len(items)} analysed • {errors} errors • five-minute refresh scheduler active'))
                self.events.put(('log',f'Coverage {ok}/{len(items)}, errors {errors}, elapsed {elapsed}s. Each row has its own candle timestamp.'))
                self.events.put(('forecast_batch',None))
                # Fixed five-minute start grid. Skip missed slots rather than overlap full scans.
                while not self.stop.is_set():
                    remaining=max(0,int(next_deadline-time.monotonic()))
                    if remaining<=0:break
                    self.events.put(('status',f'DHAN • Cached results available • {ok}/{len(items)} updated • Next refresh {remaining//60:02d}:{remaining%60:02d}'))
                    if self.stop.wait(min(5,remaining)):break
                if self.stop.is_set():break
        except Exception as exc:
            message=str(exc) if isinstance(exc,DataError) else f'Unexpected {type(exc).__name__}; scanning stopped'
            self.events.put(('reset','Scan stopped / data unavailable'))
            self.events.put(('log',message)); self.events.put(('status',message))
        finally:
            if depth_stop:depth_stop.set()
            if cache: cache.close()
            self.events.put(('done',None))
    def poll(self):
        try:
            deadline=time.monotonic()+.04
            while time.monotonic()<deadline:
                event,payload=self.events.get_nowait()
                if event=='result':
                    if not self.stop.is_set() and payload.get('run_id')==self.run_id:
                        payload['active']=True;payload['plan_active']=True;self.decorate(payload);self.results[payload['symbol']]=payload;self.render()
                        self.refresh_forecast_picker()
                        if self.auto_kronos.get() and (payload['kind']=='index' or any(x.get('matched') for x in all_strategy_rows(payload)) or payload.get('intraday_plan',{}).get('timed_eligible')):
                            self.enqueue_forecast(payload)
                elif event=='forecast_batch':
                    selected=sorted((r for r in self.results.values() if r['kind']=='stock' and (any(x.get('matched') for x in all_strategy_rows(r)))),key=lambda r:(not r.get('ai_row',{}).get('matched',False),not r.get('institutional_row',{}).get('matched',False),-r.get('prior_turnover',0),r['symbol']))[:20]
                    if self.auto_ml.get():
                        majors=[r for r in self.results.values() if r['kind']=='index']
                        training_stocks=selected or sorted((r for r in self.results.values() if r['kind']=='stock'),key=lambda r:-r.get('prior_turnover',0))[:20]
                        self.auto_training.enqueue(training_stocks+majors)
                        self.write_log(f'Auto ML queue: {len(self.auto_training.pending)} instruments; 3m models, one instrument at a time')
                    indices=[r for r in self.results.values() if r['kind']=='index' and fresh(r)]
                    self.write_log(f'Research candidates queued: {len(selected)}/20; {len(indices)} indices separately. New SMC candidates receive training priority.')
                    if self.auto_kronos.get() and not self.stop.is_set():
                        for r in indices+selected:self.enqueue_forecast(r)
                elif event=='forecast':
                    current=self.results.get(payload['symbol'])
                    if current and current['mode']==payload['mode'] and payload.get('run_id')==self.run_id and not self.stop.is_set():
                        self.forecasts[payload['symbol']]=payload
                        self.forecast_states[payload['symbol']]='UNAVAILABLE: '+payload['error'] if payload.get('error') else 'Completed'
                        if payload.get('error'):self.forecast_seen.discard((self.run_id,payload['mode'],payload['symbol'],payload['asof']))
                        self.decorate(current)
                        if current['action']!='WAIT':
                            try:self.journal_jobs.put_nowait(current.copy())
                            except queue.Full:self.write_log('Journal queue busy; research row remains visible')
                        self.render();self.show_forecasts()
                elif event=='scanx_status':
                    rid,candidates,message=payload
                    if rid==self.run_id:
                        self.scanx_info=message
                        for row in self.results.values():
                            if row.get('institutional_row') and (not candidates or row.get('cache_key','').split(':')[-1] not in candidates):row['institutional_row'].update(eligible=False,matched=False,reason=message+'; not in current verified ScanX list')
                        self.render()
                elif event=='universe':self.expected_stocks=payload;self.refresh_dashboard()
                elif event=='raw_news':
                    if payload[0]==self.run_id:
                        self.news_alerts=important(payload[1])
                        for alert in self.news_alerts:
                            if alert['id'] not in self.news_seen:
                                self.news_seen.add(alert['id']);self.bell();self.write_log('NEWS ALERT: '+alert['symbol']+' | '+alert['tags']+' | '+alert['title'])
                        self.show_ai()
                    if self.use_news.get():
                        try:self.news_jobs.put_nowait(payload)
                        except queue.Full:pass
                elif event=='news':
                    run_id,news=payload
                    if run_id==self.run_id:self.news_state=news;self.refresh_decisions();self.show_ai()
                elif event=='training':self.write_log(payload);self.show_ai(extra=payload)
                elif event=='retune_check':self.maybe_retune()
                elif event=='forecast_status':self.forecast_progress.set(payload)
                elif event=='status': self.status.set(payload)
                elif event=='log': self.write_log(payload)
                elif event=='alert': self.bell(); self.write_log(payload)
                elif event=='reset':
                    for r in self.results.values():
                        r['active']=False
                        if not payload.startswith('Refreshing'):
                            r['plan_active']=False
                            for row in all_strategy_rows(r):row.update(eligible=False,strategy_status='STOPPED / CACHED',reason=payload)
                        self.decorate(r);r['blockers']=[payload]
                    self.render();self.redraw_forecast()
                elif event=='done': self.startbutton.configure(state='normal')
        except queue.Empty: pass
        # Expire visible levels even when scans are slow or stopped.
        now=pd.Timestamp.now(tz=IST)
        changed=False
        for r in self.results.values():
            if r.get('mode')=='DHAN LIVE' and r.get('active',True) and r['candle']:
                if (now-pd.Timestamp(r['candle'])).total_seconds()>r['minutes']*60+max(180,r['minutes']*60):
                    r['active']=False;self.decorate(r);r['blockers']=['STALE / signal expired'];changed=True
        if changed:self.render();self.redraw_forecast()
        if not self.closing and not self.stop.is_set() and self.auto_ml.get() and (not self.training_worker or not self.training_worker.is_alive()):
            job=self.auto_training.pop()
            if job:self.start_training([job])
        if self.closing and (not self.worker or not self.worker.is_alive()) and (not self.training_worker or not self.training_worker.is_alive()): self.destroy(); return
        if time.monotonic()-getattr(self,'last_view_refresh',0)>1:
            self.last_view_refresh=time.monotonic();self.render()
        self.after(100,self.poll)
    def render(self):
        if not getattr(self,'render_pending',False):
            self.render_pending=True;self.after(200,self.flush_render)
    def flush_render(self):
        self.render_pending=False;self._render_now()
    def _render_now(self):
        if not hasattr(self,'tables'):return
        visible=self.book.tab(self.book.select(),'text')
        if visible=='Dashboard':self.refresh_dashboard()
        for name,tree in self.tables.items():
            if name!=visible:continue
            selected=tree.selection(); selection=selected[0] if selected else None
            if name in STRATEGY_TABS:
                allrows=[]
                for base in self.results.values():
                    if base['kind']!='stock':continue
                    values=strategy_rows(base,name)
                    for v in values:
                        v=dict(v)
                        if v.get('eligible'):
                            clock=pd.Timestamp.now(tz=IST)
                            if self.stop.is_set() or not v.get('data_at') or (clock-pd.Timestamp(v['data_at'])).total_seconds()>300 or (v.get('valid_until') and clock>pd.Timestamp(v['valid_until'])):v.update(eligible=False,strategy_status='STALE / ENTRY WINDOW CLOSED',reason='Cached result only; wait for the next background refresh')
                        v=compact(v,name);v['row_id']=v['symbol']+'|'+v['strategy'];allrows.append(v)
                rows=sorted((r for r in allrows if r.get('matched') or self.show_blocked.get()),key=lambda r:(not r.get('eligible',False),r['symbol'],r['strategy']))
                for r in rows:self.strategy_lookup[(name,r['row_id'])]=r
                from collections import Counter
                reasons=Counter(r.get('reason','Waiting') for r in allrows if not r.get('eligible'))
                self.scan_labels[name].configure(text=(getattr(self,'scanx_info','Waiting for ScanX snapshot')+' | ' if name=='Institutional stocks' else '')+f"{sum(bool(r.get('eligible')) for r in allrows)} READY / {sum(bool(r.get('matched')) for r in allrows)} patterns / {len(allrows)} evaluated. "+' | '.join(f'{n}: {why}' for why,n in reasons.most_common(2)))
            elif name=='Intraday Top 10':
                rows=ranked(self.results.values(),limit=10,intraday=True);self.scan_labels[name].configure(text=scan_status(self.results.values(),True))
            else:rows=[r for r in self.results.values() if r['kind']!='stock']
            rows=[compact(r,name) for r in rows]
            keep={r.get('row_id',r['symbol']) for r in rows}
            for iid in tree.get_children():
                if iid not in keep:tree.delete(iid)
            for i,r in enumerate(rows):
                values=[]
                for c in self.table_columns[name]:
                    v=r.get(c)
                    if c=='candle': v=v[11:19]+' IST' if v else '—'
                    values.append('—' if v is None else f'{v:.2f}' if isinstance(v,float) else v)
                tag='buy' if r.get('eligible') or r.get('action')=='BUY SETUP' else 'sell' if r.get('action')=='SELL SETUP' else 'wait'
                iid=r.get('row_id',r['symbol'])
                fingerprint=(tuple(values),tag)
                if tree.exists(iid):
                    if self.rendered_values.get((name,iid))!=fingerprint:tree.item(iid,values=values,tags=(tag,))
                    tree.move(iid,'',i)
                else:tree.insert('','end',iid=iid,values=values,tags=(tag,))
                self.rendered_values[(name,iid)]=fingerprint
            if selection and tree.exists(selection): tree.selection_set(selection)
    def select(self,event):
        choice=event.widget.selection()
        if not choice:return
        for name in STRATEGY_TABS:
            if event.widget==self.tables.get(name):
                r=self.strategy_lookup.get((name,choice[0]),{});self.strategy_selection=r;self.selected_symbol=r.get('symbol');self.show_ai()
                self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',details(r));self.detail.configure(state='disabled')
                self.draw(self.results.get(self.selected_symbol,{}).get('chart',[]));return
        self.strategy_selection=None
        self.selected_symbol=choice[0]
        r=self.results[choice[0]]
        if event.widget==self.tables.get('Intraday Top 10'):r={**r,**r.get('intraday_plan',{})}
        self.show_ai()
        if r['symbol'] in self.forecasts:self.forecast_symbol.set(r['symbol']);self.redraw_forecast()
        text=f"{r['symbol']} | {r['mode']} | {r['action']}\nAgreement: {r['score']}/100 (not probability)\n15/30/60m: {r['htf']}\nCandle: {r['candle']}\n"
        if r['symbol'] in self.forecasts:
            k=self.forecasts[r['symbol']]; text+=f"Kronos: {k.get('bias','UNAVAILABLE')} | as of {k.get('asof','—')}\n"
        text+=f"ML: {r.get('ml_status','NOT TRAINED')} | {r.get('risk_overlay',{}).get('status','NEWS UNKNOWN')}\n"
        text+=f"Checks: {r.get('confirmation')} | Technical {r.get('technical_check')} | Fundamental {r.get('fundamental_check')} | Kronos {r.get('kronos_check')}\n"
        text+=f"\nMORNING PLAN (conditional): {r.get('plan_status')} | {r.get('plan_direction')} | prior session {r.get('prior_date')}\nEntry {r.get('plan_entry')} | Stop {r.get('plan_stop')} | T1 {r.get('plan_t1')} | T2 {r.get('plan_t2')}\nPlans are not confirmed signals. SHORT is research only; no delivery short orders.\n"
        text+=f"\nDaily: {r.get('daily_bias','—')} | Weekly: {r.get('weekly_bias','—')} | Release: {r.get('scan_release','—')}\nMorning analysis: {r.get('scan_reason','—')}\nIntraday analysis: {r.get('intraday_plan',{}).get('scan_reason','—')}\n"
        text+='\nFundamental details:\n'+'\n'.join(r.get('fundamentals',{}).get('reasons',[]))
        text+='\nEvidence:\n'+'\n'.join('• '+x for x in r['reasons'])
        text+='\n\nWaiting / risk filters:\n'+'\n'.join('• '+x for x in r['blockers'])
        if r['kind']=='index': text+='\nIndex volume unavailable: VWAP/RVOL votes excluded.'
        self.detail.configure(state='normal'); self.detail.delete('1.0','end'); self.detail.insert('1.0',text); self.detail.configure(state='disabled')
        self.draw(r['chart'])
    def draw(self,rows):
        c=self.canvas; c.delete('all'); w=max(c.winfo_width(),400); h=190
        if not rows:return
        low=min(r['low'] for r in rows); high=max(r['high'] for r in rows); span=max(high-low,.01)
        y=lambda p: 22+(high-p)/span*(h-45)
        for i,r in enumerate(rows):
            x=12+i*(w-65)/len(rows); color=GREEN if r['close']>=r['open'] else '#ff8f9c'
            c.create_line(x,y(r['high']),x,y(r['low']),fill=color)
            c.create_rectangle(x-2,y(max(r['open'],r['close'])),x+2,max(y(min(r['open'],r['close'])),y(max(r['open'],r['close']))+1),fill=color,outline=color)
        c.create_text(w-4,18,text=f'{high:.2f}',anchor='ne',fill=MUTED); c.create_text(w-4,h-20,text=f'{low:.2f}',anchor='ne',fill=MUTED)
        c.create_text(10,5,text='Closed candles • IST',anchor='nw',fill=MUTED)
    def predict_selected(self):
        if self.selected_symbol in self.results:
            self.enqueue_forecast(self.results[self.selected_symbol]); return
        messagebox.showinfo('Select instrument','Select a stock or index row first.')
    def refresh_forecast_picker(self):
        names=sorted(set(self.results)|set(self.forecasts))
        self.forecast_picker.configure(values=names)
        if self.forecast_symbol.get() not in names:self.forecast_symbol.set(names[0] if names else '')
        self.redraw_forecast()
    def predict_dropdown(self):
        symbol=self.forecast_symbol.get()
        if symbol not in self.results:
            self.forecast_progress.set('Start a scan first; instruments appear as data arrives.');return
        self.enqueue_forecast(self.results[symbol])
    def forecast_notice(self,symbol,message):
        self.forecast_states[symbol]=message
        self.forecast_progress.set(symbol+' • '+message)
        self.write_log('Kronos '+symbol+': '+message)
        self.redraw_forecast()
    def enqueue_forecast(self,r):
        symbol=r['symbol']
        if self.stop.is_set():
            self.forecast_notice(symbol,'Scanner stopped. Start the scan before requesting a forecast.');return False
        if not r.get('context'):
            self.forecast_notice(symbol,'Waiting for at least 60 complete chart candles. Choose 3/5/15m or collect more history.');return False
        if not fresh(r):
            self.forecast_notice(symbol,'Input candles are stale or refreshing. Wait for the next five-minute scan.');return False
        key=(self.run_id,r['mode'],symbol,r['candle'])
        if key in self.forecast_seen:
            self.forecast_notice(symbol,'Already queued or completed for this candle; wait for the result or a new candle.');return False
        if self.forecast_jobs.put((r.copy(),r['minutes'])):
            self.forecast_seen.add(key)
            if len(self.forecast_seen)>5000:self.forecast_seen={key}
            self.forecast_notice(symbol,'Queued for local Kronos prediction');return True
        self.forecast_notice(symbol,'Queue full. Wait for pending forecasts, then retry.');return False
    def forecast_loop(self):
        forecaster=Forecaster()
        while True:
            r,minutes=self.forecast_jobs.get()
            if r.get('run_id')!=self.run_id or self.stop.is_set():continue
            self.events.put(('forecast_status',f"Predicting {r['symbol']} • {self.forecast_jobs.size()} queued • local model"))
            try:
                if r['mode']=='DHAN LIVE' and (pd.Timestamp.now(tz=IST)-pd.Timestamp(r['candle'])).total_seconds()>minutes*60+180:
                    raise ForecastError('Input candles are stale; wait for next scan')
                f=pd.DataFrame(r['context']); f.index=pd.to_datetime(f.pop('time'),utc=True).dt.tz_convert(IST)
                result=forecaster.predict(f,minutes=minutes)
                result.update(run_id=r['run_id'],history=r['chart'],minutes=minutes,symbol=r['symbol'],mode=r['mode'],generated=pd.Timestamp.now(tz=IST).isoformat())
                self.events.put(('forecast',result))
                self.events.put(('forecast_status',f"Completed {r['symbol']} • {self.forecast_jobs.size()} queued"))
            except Exception as exc:
                message=str(exc) if isinstance(exc,ForecastError) else type(exc).__name__+' during inference'
                self.events.put(('log','Kronos '+r['symbol']+': '+message))
                self.events.put(('forecast',dict(run_id=r['run_id'],history=r['chart'],symbol=r['symbol'],mode=r['mode'],error=message,asof=r['candle'])))
    def redraw_forecast(self):
        if not hasattr(self,'forecast_canvas'):return
        symbol=self.forecast_symbol.get();f=self.forecasts.get(symbol)
        label=symbol+' | '+(f.get('mode','') if f else '')
        if not f:
            message=self.forecast_states.get(symbol,'Select an instrument, then click Forecast this instrument.' if symbol else 'Start a scan. Instruments will appear here as data arrives.')
            f={'error':message}
        if f and not f.get('error'):
            r=self.results.get(symbol,{})
            current=f.get('asof')==r.get('candle') and fresh(r)
            label+=' | '+('CURRENT SNAPSHOT' if current else 'HISTORICAL / STALE')+' | as of '+f.get('asof','')
        draw_forecast(self.forecast_canvas,(f or {}).get('history',[]),f,label)
    def show_forecasts(self):
        self.refresh_forecast_picker()
        self.redraw_forecast()
        lines=['KRONOS • TOP 20 MOMENTUM + INDICES • THREE-CHECK RESEARCH SCREEN',
               'Forecast as-of timestamps identify the input snapshot. Old forecasts are historical, never live signals.',
               'Three sampled paths; their range is not a calibrated confidence interval.\n']
        for symbol,k in self.forecasts.items():
            lines.append(symbol+' | '+k['mode']+' | input as of '+k['asof'])
            if 'error' in k: lines.append('UNAVAILABLE: '+k['error']+'\n'); continue
            lines.append(f"{k['model']} | {k['bias']} | median final change {k['change_pct']:+.2f}%")
            lines.append(f"Kronos K1: {k.get('kronos_t1','—')} | K2: {k.get('kronos_t2','—')} | {k.get('target_note','')}")
            lines.append('Future candle IST        Median close       Sample range')
            for t,m,lo,hi in zip(k['timestamps'],k['median'],k['low'],k['high']):
                lines.append(f'{t[11:16]}                         {m:.2f}                {lo:.2f} – {hi:.2f}')
            lines.append(k['note']+'\n')
        self.forecast_text.configure(state='normal'); self.forecast_text.delete('1.0','end'); self.forecast_text.insert('1.0','\n'.join(lines)); self.forecast_text.configure(state='disabled')
    def decorate(self,r):
        r['ml_required']=self.ml_required.get();r['ml_status']=r.get('ml',{}).get('status','NOT TRAINED')
        r['ml_probability']=r.get('ml',{}).get('probability')
        direction='LONG' if r.get('bias')=='BULL' else 'SHORT'
        r['risk_overlay']=risk_overlay(self.news_state,r['symbol'],direction)
        forecast=self.forecasts.get(r['symbol'])
        confirm(r,forecast)
        matching=forecast and not forecast.get('error') and forecast.get('asof')==r.get('candle') and forecast.get('mode')==r.get('mode') and fresh(r)
        for key in ('kronos_t1','kronos_t2'):r[key]=forecast.get(key) if matching else None
        try:capital=float(self.capital.get());pct=float(self.risk_pct.get())
        except ValueError:capital=pct=0
        r['paper_units']=suggested_units(capital,pct,r.get('entry'),r.get('stop'),r['risk_overlay']['factor'],r['kind']) if r['action']!='WAIT' else None
    def refresh_decisions(self):
        for r in self.results.values():self.decorate(r)
        if hasattr(self,'tables'):self.render()
    def refresh_dashboard(self):
        if not hasattr(self,'dashboard'):return
        data=summary(self.results.values(),self.expected_stocks)
        ml_count=sum(r.get('ml',{}).get('pass_gate',False) and fresh(r) for r in self.results.values())
        draw_dashboard(self.dashboard,data,ml_count)
    def collect_news(self,client,token,items,stop,run_id):
        api=Dhan(client,token,stop);offset=0
        majors={'RELIANCE','HDFCBANK','ICICIBANK','INFY','TCS','SBIN','LT','BHARTIARTL'}
        stocks=[x for x in items if x['kind']=='stock'];big=[x['id'] for x in stocks if x['symbol'] in majors]
        while not stop.is_set():
            started=time.monotonic()
            try:
                ids=list(dict.fromkeys(big+[x['id'] for x in stocks[offset:offset+20]]));offset=(offset+20)%max(1,len(stocks))
                articles=api.news(macro=True)+api.news(ids)
                self.events.put(('raw_news',(run_id,articles)));self.events.put(('log','News refresh completed; next scheduled fetch in 5 minutes. Coverage is the returned feed, not every article.'))
            except Exception as exc:self.events.put(('log','News feed unavailable: '+type(exc).__name__))
            if stop.wait(max(1,next_refresh(started,time.monotonic())-time.monotonic())):break
    def import_risk_data(self):
        path=filedialog.askopenfilename(title='Import dated NSE ban/delivery CSV or reviewed risk_calendar.json',filetypes=[('Risk data','*.csv *.json')])
        if not path:return
        try:
            source=Path(path);folder=ROOT/'safety';folder.mkdir(parents=True,exist_ok=True)
            if source.suffix.lower()=='.json':
                obj=json.loads(source.read_text());check=event_gate(obj,'TEST',pd.Timestamp.now(tz=IST))
                if 'INVALID' in check:raise ValueError('Invalid reviewed event calendar schema; see template')
                dest=folder/'risk_calendar.json'
            else:
                import re
                hit=re.search(r'(\d{8})',source.name)
                if not hit:raise ValueError('NSE CSV filename must contain DDMMYYYY report date')
                day=pd.to_datetime(hit.group(1),format='%d%m%Y').date();text=source.read_text(encoding='utf-8-sig')
                ban='secban' in source.name.lower();obj=(parse_ban if ban else parse_delivery)(text,day);dest=folder/(('ban_' if ban else 'delivery_')+str(day)+'.json')
            tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(obj));tmp.replace(dest);self.write_log('Imported risk data. Applied on the next scan.')
        except Exception as exc:messagebox.showerror('Import rejected',str(exc))
    def track_strategy(self):
        r=self.strategy_selection
        if r:
            base=self.results.get(r['symbol'],{})
            r=next((x for x in all_strategy_rows(base) if x.get('strategy')==r.get('strategy')),None)
        if r and (r.get('strategy','').startswith('SMC') or r.get('strategy') in ('Institutional RSI pullback','RSI pullback + confirmation')):
            messagebox.showinfo('Research row','These new tabs provide research levels only; paper-watch exits are not implemented for these strategies.');return
        if not r or not r.get('eligible'):messagebox.showinfo('Select a ready row','Select a READY strategy row first. This creates a PAPER watch only.');return
        try:
            if (pd.Timestamp.now(tz=IST)-pd.Timestamp(r['data_at'])).total_seconds()>300 or (r.get('valid_until') and pd.Timestamp.now(tz=IST)>pd.Timestamp(r['valid_until'])):raise ValueError('Row is stale or entry window closed; wait for background refresh')
            price=r.get('premium_entry') if r.get('option_id') else r.get('underlying_entry')
            entry=simpledialog.askfloat('Paper entry','Enter simulated fill price (no broker order):',initialvalue=price,minvalue=.01)
            if entry is None:return
            qty=int(r.get('quantity',0))
            if qty<=0:raise ValueError('No quantity fits risk budget')
            self.paper_watch.add(r,entry,qty,self.time_only.get());self.write_log(f"PAPER watch added: {r['symbol']}, quantity {qty}. Alerts are periodic; no broker exit is sent.")
        except Exception as exc:messagebox.showerror('Paper watch',str(exc))
    def paper_positions(self):
        top=tk.Toplevel(self);top.title('Paper positions - no broker orders');text=tk.Text(top,width=100,height=30,bg=PANEL,fg=TEXT);text.pack(fill='both',expand=True);text.insert('1.0',json.dumps(self.paper_watch.read(),indent=2,ensure_ascii=False))
        def clear():
            if messagebox.askyesno('Clear paper watches','Remove all paper watches? This does not close any broker positions.'):
                with self.paper_watch.lock:self.paper_watch.save([])
                top.destroy()
        ttk.Button(top,text='Clear paper watches',command=clear).pack()
    def depth_loop(self,client,token,items,stop,run_id):
        api=Dhan(client,token,stop);cache=Cache(ROOT);failures=0
        try:
            while not stop.is_set():
                started=time.monotonic()
                clock=pd.Timestamp.now(tz=IST)
                if clock.weekday()>=5 or not 555<=clock.hour*60+clock.minute<930:
                    if stop.wait(300):break
                    continue
                try:
                    quotes=api.quotes(items);received=pd.Timestamp.now(tz=IST);stored=0
                    for it in items:stored+=cache.save_book(it['segment']+':'+it['id'],quotes.get(it['segment'],{}).get(it['id'],{}),received,commit=False)
                    cache.db.execute('DELETE FROM book WHERE ts < ?',((received-pd.Timedelta(days=90)).timestamp(),));cache.db.commit();failures=0
                    if stored==0:self.events.put(('log','Depth snapshots: no fresh valid stock order books in this response.'))
                except DataError as exc:
                    failures+=1;self.events.put(('log','Depth collector: '+str(exc)))
                    if failures>=3:break
                if stop.wait(max(1,next_refresh(started,time.monotonic())-time.monotonic())):break
        finally:cache.close()
    def journal_loop(self):
        while True:
            row=self.journal_jobs.get();cache=None
            try:
                cache=Cache(ROOT)
                if cache.record(row,row['mode']):self.events.put(('log','CHECKS PASSED: '+row['symbol']+' '+row['action']))
            except Exception as exc:self.events.put(('log','Background journal unavailable: '+type(exc).__name__))
            finally:
                if cache:cache.close()
                self.journal_jobs.task_done()
    def news_loop(self):
        service=SentimentService()
        while True:
            run_id,items=self.news_jobs.get()
            if run_id!=self.run_id or self.stop.is_set():continue
            self.events.put(('log','FinBERT processing available news text locally…'))
            result=service.analyze(items);self.events.put(('news',(run_id,result)))
    def show_ai(self,extra=''):
        if not hasattr(self,'ai_text'):return
        lines=['AI RESEARCH DESK  /  LightGBM + XGBoost + FinBERT',
               'ML is an additional gate. Statistical validation is not proof of profitability.',
               'Optuna tunes offline with chronological purging. SHAP values explain model output, not causes.\n',extra]
        r=self.results.get(self.selected_symbol,{})
        if r:
            m=r.get('ml',{});lines += [r['symbol']+' — '+m.get('status','NOT TRAINED'),
                'LightGBM raw P: '+str(m.get('lightgbm','—'))+' | XGBoost raw P: '+str(m.get('xgboost','—')),
                'Calibrated target-event P: '+str(m.get('probability','—')),
                'ML timeframe: 3 minutes (independent of selected chart timeframe).',
                'Target: +1.5 ATR before -1 ATR over next 10 bars, next-bar open entry.',
                'Order-book features used: '+str(m.get('book_enabled',False))]
            lines += [f"SHAP {x['feature']}: {x['contribution']:+.4f} raw log-odds" for x in m.get('shap',[])]
            risk=r.get('risk_overlay',{});lines += ['News: '+risk.get('status','UNKNOWN')+' | risk multiplier: '+str(risk.get('factor',.5)),
                'Illustrative paper units: '+str(r.get('paper_units','—'))+' (no index lot sizing, no leverage, no order)']
            report=m.get('report',{})
            if report:lines += ['Validation: '+json.dumps({k:report.get(k) for k in ('status','test_auc','test_brier','baseline_brier','rows')})]
        lines += ['\nIMPORTANT NEWS / EVENT ALERTS (5-minute fetch; impact is a hypothesis):']
        for n in self.news_alerts[:30]:lines.append(f"{n['published']} | {n['symbol']} | {n['tags']} | {n['title']}\nImpact review: {n['impact']}\nSource: {n['source']}")
        lines += ['\nNEWS FEED: '+self.news_state.get('status','Not loaded; connect Dhan live and install FinBERT dependencies')]
        for n in self.news_state.get('items',[])[:20]:lines.append(f"{n['published']} | {n.get('symbol') or 'macro'} | sentiment {n['score']:+.2f} | {n['title']}")
        self.ai_text.configure(state='normal');self.ai_text.delete('1.0','end');self.ai_text.insert('1.0','\n'.join(lines));self.ai_text.configure(state='disabled')
    def train_selected(self):
        r=self.results.get(self.selected_symbol)
        if not r:messagebox.showinfo('Select instrument','Select a stock or index row first.');return
        self.start_training([r])
    def start_training(self,rows):
        if self.training_worker and self.training_worker.is_alive():self.write_log('Training already running.');return
        rows=[r.copy() for r in rows if r.get('mode')=='DHAN LIVE' and r.get('cache_key')]
        if not rows:messagebox.showinfo('Live data required','Collect Dhan history first. Demo data cannot activate trading models.');return
        training_run=self.run_id
        def work():
            for r in rows:
                if self.closing or self.stop.is_set() or training_run!=self.run_id:break
                try:
                    cache=Cache(ROOT)
                    try:f=cache.load(r['cache_key']);book=cache.load_book(r['cache_key'])
                    finally:cache.close()
                    if f is None:raise ValueError('No history')
                    b=bars(f,3,pd.Timestamp.now(tz=IST))
                    for direction in ('LONG','SHORT'):
                        if self.closing or self.stop.is_set() or training_run!=self.run_id:break
                        self.events.put(('training',f"Training {r['symbol']} {direction}; Optuna 12 trials, two inner chronological folds…"))
                        report=train(b,ROOT,r['symbol'],3,direction,book,trials=12)
                        self.events.put(('training',r['symbol']+' '+direction+': '+report['status']+' | Brier '+str(round(report['test_brier'],4))))
                    self.events.put(('training','Finished. Models apply only to bars after their validation cutoff on subsequent scans.'))
                except Exception as exc:self.events.put(('training','Training blocked: '+type(exc).__name__+': '+str(exc)[:200]))
        self.training_worker=threading.Thread(target=work,daemon=True);self.training_worker.start()
    def maybe_retune(self):
        now=pd.Timestamp.now(tz=IST)
        if not self.auto_tune.get() or now.weekday()>=5 or (now.hour*60+now.minute)<935 or self.last_auto_train==str(now.date()):return
        if self.training_worker and self.training_worker.is_alive():return
        due=[r for r in self.results.values() if r.get('mode')=='DHAN LIVE' and r.get('ml',{}).get('status') in ('NOT TRAINED','RETRAIN DUE','DRIFT / RETRAIN DUE')]
        due=sorted(due,key=lambda r:-r.get('momentum',0))[:3]
        if due:self.last_auto_train=str(now.date());self.start_training(due)
    def export(self):
        if not self.results:return
        path=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='fusion_scan.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        name=self.book.tab(self.book.select(),'text')
        self._render_now()
        if name in STRATEGY_TABS:
            rows=[self.strategy_lookup[(name,i)] for i in self.tables[name].get_children()]
            cols=list(COLUMNS)
        else:
            rows=list(self.results.values())
            cols=list(self.columns)+['technical_action','technical_check','mode','observed','reasons','blockers']
        with open(path,'w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=cols); writer.writeheader()
            for r in rows:
                row={k:'; '.join(r.get(k,[])) if isinstance(r.get(k),list) else r.get(k) for k in cols}
                for k,v in row.items():
                    if isinstance(v,str) and v.startswith(('=','+','-','@')): row[k]="'"+v
                writer.writerow(row)
        self.write_log('Table exported to chosen CSV file.')
    def close(self):
        self.stop.set(); self.token.set(''); self.closing=True; self.status.set('Closing safely; waiting for network request to finish…')

if __name__=='__main__': App().mainloop()
