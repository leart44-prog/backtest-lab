#!/usr/bin/env python3
"""
PEAD (Post-Earnings-Announcement-Drift) backtest  —  self-contained.

Reads committed data in ./data/ and writes ./results/ (JSON + 3 PNG charts).
No network needed.  Reproduce the raw data with fetch_data.py (documents sources).

Method (point-in-time safe):
  * Signal      = analyst earnings surprise, Surprise% = (ReportedEPS-EstimateEPS).
  * Entry       = CLOSE of the first full trading day AFTER the announcement is public
                  (AMC -> next session, BMO -> announcement-day session).  This SKIPS the
                  announcement jump and trades only the subsequent *drift*.
  * Drift return= adjusted-close return from entry to entry+k trading days.
  * Market-adj  = stock return minus SPY return over identical dates.
  * Event study = mean SPY-hedged drift path per full-sample surprise quintile (descriptive).
  * Tradeable   = long top / short bottom surprise names, breakpoints from a TRAILING
                  120-day surprise distribution (no look-ahead); equal weight, SPY-hedged
                  (market neutral); net of transaction costs.
"""
from pathlib import Path
import pandas as pd, numpy as np, json
pd.options.mode.chained_assignment=None

HERE=Path(__file__).resolve().parent
DATA=HERE/"data"; OUT=HERE/"results"; OUT.mkdir(exist_ok=True)
HOLD=[1,5,10,20,40,60]; PRIMARY=20; COST_BPS=5.0; START="2023-01-01"; MAXD=60

# ---------- load ----------
ev=pd.read_csv(DATA/"earnings_events.csv", parse_dates=["ann_date"])
panel=pd.read_csv(DATA/"prices_panel.csv.gz", parse_dates=["date"]).sort_values(["ticker","date"])
pdata={}
for t,g in panel.groupby("ticker"):
    g=g.drop_duplicates("date").sort_values("date")
    pdata[t]={"dates":g["date"].values,"adj":g["adj"].astype(float).values}
spy=pdata["SPY"]; spy_s=pd.Series(spy["adj"],index=pd.to_datetime(spy["dates"]))

def fwd(t,ann,session,k):
    d=pdata.get(t)
    if d is None: return None
    dates=d["dates"]; adj=d["adj"]; a=np.datetime64(pd.Timestamp(ann))
    i0=np.searchsorted(dates,a,side="right") if session=="amc" else np.searchsorted(dates,a,side="left")
    ie=i0+k
    if i0>=len(dates) or ie>=len(dates) or adj[i0]<=0 or adj[ie]<=0: return None
    return pd.Timestamp(dates[i0]),pd.Timestamp(dates[ie]),adj[ie]/adj[i0]-1.0,i0

def spy_ret(d0,d1):
    try:
        a=spy_s.asof(d0); b=spy_s.asof(d1)
        if a>0 and b>0: return b/a-1.0
    except Exception: pass
    return np.nan

# ---------- event table ----------
ev=ev[(ev["ann_date"]>=pd.Timestamp(START)) & ev["surp"].notna()]
rows=[]
for _,r in ev.iterrows():
    base=fwd(r["ticker"],r["ann_date"],r["session"],1)
    if base is None: continue
    rec=dict(ticker=r["ticker"],ann_date=r["ann_date"],session=r["session"],
             surp=r["surp"],entry_date=base[0],entry_idx=base[3])
    for k in HOLD:
        f=fwd(r["ticker"],r["ann_date"],r["session"],k)
        rec[f"r{k}"]=np.nan if f is None else f[2]
        rec[f"mr{k}"]=np.nan if f is None else f[2]-spy_ret(f[0],f[1])
    rows.append(rec)
df=pd.DataFrame(rows).dropna(subset=[f"mr{PRIMARY}"]).reset_index(drop=True)
df["year"]=df["ann_date"].dt.year
df["q"]=pd.qcut(df["surp"],5,labels=[1,2,3,4,5]).astype(int)
print(f"[events used] {len(df)} tickers={df['ticker'].nunique()} "
      f"{df['ann_date'].min().date()}..{df['ann_date'].max().date()}")

study={k:{int(q):round(v*100,3) for q,v in df.groupby('q')[f'mr{k}'].mean().items()} for k in HOLD}
ls_by_k={k:round((df[df.q==5][f'mr{k}'].mean()-df[df.q==1][f'mr{k}'].mean())*100,3) for k in HOLD}

# ---------- daily returns + SPY-by-calendar ----------
cal=np.array(sorted(panel["date"].unique())); cal_idx={pd.Timestamp(d):i for i,d in enumerate(cal)}
spy_daily=np.full(len(cal),np.nan)
for dt,v in pd.Series(spy["adj"],index=pd.to_datetime(spy["dates"])).pct_change().items():
    ci=cal_idx.get(pd.Timestamp(dt))
    if ci is not None: spy_daily[ci]=v
dret={t:pd.Series(d["adj"]).pct_change().values for t,d in pdata.items()}
cost=COST_BPS/1e4

# ---------- event-study cumulative SPY-hedged drift paths ----------
paths={q:np.zeros(MAXD+1) for q in range(1,6)}; pathn={q:np.zeros(MAXD+1) for q in range(1,6)}
for _,r in df.iterrows():
    t=r["ticker"]; i0=int(r["entry_idx"]); rr=dret[t]; ds=pdata[t]["dates"]; q=int(r["q"]); cum=0.0
    for h in range(MAXD+1):
        j=i0+h
        if j>=len(ds): break
        if h>0 and not np.isnan(rr[j]):
            ci=cal_idx.get(pd.Timestamp(ds[j])); rm=spy_daily[ci] if ci is not None else 0.0
            cum+=rr[j]-(0.0 if np.isnan(rm) else rm)
        paths[q][h]+=cum; pathn[q][h]+=1
drift={q:paths[q]/np.maximum(pathn[q],1)*100 for q in range(1,6)}

# ---------- PIT-safe tradeable signal ----------
df=df.sort_values("entry_date").reset_index(drop=True)
sv=df["surp"].values; ed=df["entry_date"].values; sig=[]
for i in range(len(df)):
    hist=sv[(ed<ed[i])&(ed>=ed[i]-np.timedelta64(120,"D"))]
    if len(hist)>=40:
        lo,hi=np.percentile(hist,[20,80]); sig.append(1 if sv[i]>=hi else (-1 if sv[i]<=lo else 0))
    else: sig.append(0)
df["signal"]=sig; traded=df[df.signal!=0]
print(f"[traded] {len(traded)} long={int((traded.signal==1).sum())} short={int((traded.signal==-1).sum())}")

def hedged_ls(H):
    la=np.zeros(len(cal)); lc=np.zeros(len(cal)); sa=np.zeros(len(cal)); sc=np.zeros(len(cal))
    for _,r in traded.iterrows():
        t=r["ticker"]; i0=int(r["entry_idx"]); rr=dret[t]; ds=pdata[t]["dates"]; sgn=r["signal"]
        for j in range(i0+1,min(i0+1+H,len(ds))):
            if np.isnan(rr[j]): continue
            ci=cal_idx.get(pd.Timestamp(ds[j]))
            if ci is None: continue
            rm=spy_daily[ci]; h=rr[j]-(0.0 if np.isnan(rm) else rm)
            if sgn==1: la[ci]+=h; lc[ci]+=1
            else: sa[ci]+=h; sc[ci]+=1
    long_a=np.divide(la,lc,out=np.zeros_like(la),where=lc>0)
    short_a=np.divide(sa,sc,out=np.zeros_like(sa),where=sc>0)
    act=(lc>0)|(sc>0); ls=long_a-short_a; ls[act]-=2*cost/H
    return ls,act,long_a,short_a,lc,sc

def stats(d,m):
    d=d[m]
    if len(d)==0: return {}
    eq=np.cumprod(1+d); peak=np.maximum.accumulate(eq)
    return dict(days=int(len(d)),total_ret=round((eq[-1]-1)*100,2),
                ann_ret=round((eq[-1]**(252/len(d))-1)*100,2),
                ann_vol=round(d.std()*np.sqrt(252)*100,2),
                sharpe=round((d.mean()*252)/(d.std()*np.sqrt(252)+1e-12),2),
                max_dd=round((eq/peak-1).min()*100,2))

ls20,a20,la20,sa20,lc20,sc20=hedged_ls(20); ls60,a60,la60,sa60,lc60,sc60=hedged_ls(60)
spy_d=pd.Series(spy["adj"],index=pd.to_datetime(spy["dates"])).pct_change().dropna()
spy_d=spy_d[spy_d.index>=pd.Timestamp(traded["entry_date"].min())]
def leg(x): x=x.dropna(); return dict(n=int(len(x)),mean_pct=round(x.mean()*100,3),hit=round((x>0).mean()*100,1))

out=dict(
 universe=dict(events_used=int(len(df)),tickers=int(df['ticker'].nunique()),
   period=f"{df['ann_date'].min().date()}..{df['ann_date'].max().date()}",
   price_period=f"{panel['date'].min().date()}..{panel['date'].max().date()}",
   cost_bps_per_side=COST_BPS,primary_horizon_days=PRIMARY),
 event_study_marketadj_pct=study, long_short_spread_pct=ls_by_k,
 traded=dict(n=int(len(traded)),longs=int((traded.signal==1).sum()),shorts=int((traded.signal==-1).sum()),
   long_leg_drift20=leg(traded[traded.signal==1]["mr20"]),
   short_leg_drift20_for_short=leg(-traded[traded.signal==-1]["mr20"])),
 portfolio_marketneutral=dict(long_short_hedged_20d=stats(ls20,a20),
   long_short_hedged_60d=stats(ls60,a60),
   long_leg_alpha_60d=stats(np.where(lc60>0,la60-2*cost/60,0.0),lc60>0),
   short_leg_alpha_60d=stats(np.where(sc60>0,-sa60-2*cost/60,0.0),sc60>0),
   spy_buyhold_reference=stats(spy_d.values,np.ones(len(spy_d),bool))),
 by_year_LS_spread_mr20_pct={int(y):round((g[g.q==5]['mr20'].mean()-g[g.q==1]['mr20'].mean())*100,3) for y,g in df.groupby('year')},
 by_year_LS_spread_mr60_pct={int(y):round((g[g.q==5]['mr60'].mean()-g[g.q==1]['mr60'].mean())*100,3) for y,g in df.groupby('year')},
)
json.dump(out,open(OUT/"results.json","w"),indent=2,default=str)

# ---------- charts ----------
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams.update({"figure.dpi":120,"font.size":9})
col={1:"#d62728",2:"#ff9896",3:"#7f7f7f",4:"#98df8a",5:"#2ca02c"}
lab={1:"Q1 (most negative surprise)",2:"Q2",3:"Q3",4:"Q4",5:"Q5 (most positive surprise)"}
fig,ax=plt.subplots(figsize=(7,4.2))
for q in range(1,6): ax.plot(range(MAXD+1),drift[q],color=col[q],label=lab[q],lw=1.8)
ax.axhline(0,color="k",lw=.6); ax.set_xlabel("Trading days after PEAD entry")
ax.set_ylabel("Cumulative SPY-hedged return (%)")
ax.set_title("PEAD drift by earnings-surprise quintile (S&P500, 2023-2025)")
ax.legend(fontsize=7,loc="lower left"); ax.grid(alpha=.3); fig.tight_layout()
fig.savefig(OUT/"fig_drift_curves.png")
fig,ax=plt.subplots(figsize=(6,3.8)); sp=[ls_by_k[k] for k in HOLD]
ax.bar([str(k) for k in HOLD],sp,color=["#2ca02c" if v>=0 else "#d62728" for v in sp])
ax.set_xlabel("Holding horizon (trading days)"); ax.set_ylabel("Q5-Q1 market-adj spread (%)")
ax.set_title("PEAD long-short spread vs horizon"); ax.grid(alpha=.3,axis="y"); fig.tight_layout()
fig.savefig(OUT/"fig_spread_termstructure.png")
fig,ax=plt.subplots(figsize=(7,4.2))
for daily,m,l,c in [(ls20,a20,"L/S hedged, 20d hold","#1f77b4"),(ls60,a60,"L/S hedged, 60d hold","#2ca02c")]:
    idx=np.where(m)[0]; ax.plot(cal[idx].astype("datetime64[D]"),(np.cumprod(1+daily[m])-1)*100,label=l,c=c,lw=1.6)
ax.axhline(0,color="k",lw=.6); ax.set_ylabel("Cumulative return (%)")
ax.set_title("Market-neutral PEAD long/short equity (net of 5bp/side costs)")
ax.legend(fontsize=8); ax.grid(alpha=.3); fig.tight_layout()
fig.savefig(OUT/"fig_equity_marketneutral.png")
print("wrote", OUT/"results.json", "+ 3 charts")
