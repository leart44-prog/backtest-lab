#!/usr/bin/env python3
"""
Reproduce the raw PEAD datasets in ./data/ from public GitHub-hosted sources.

Why GitHub-hosted data?  This environment's network policy only permits PyPI and
github.com / raw.githubusercontent.com.  All conventional market-data APIs
(Yahoo Finance, Nasdaq, SEC EDGAR, AlphaVantage, FMP, stooq) are blocked (HTTP 403),
so the data below is pulled from public datasets that other authors committed to GitHub.

SOURCES
-------
1. Earnings surprises (Reported vs Estimate EPS, with announcement timestamps):
   github.com/Chinar-byte/FINS3666-Group-Project  ->  earnings_data/<TICKER>_earnings.csv
   (yfinance `get_earnings_dates()` exports for ~230 S&P 500 names, 2021-2025)

2. Daily adjusted prices (merged for 2023-01 .. 2026-04 coverage):
   github.com/magiccpp/price_data                 ->  <TICKER>.csv          (2023-01..2025-05)
   github.com/do0405/invest-prototype             ->  data/us/<TICKER>.csv  (2024-12..2026-04)

NOTE: these are third-party datasets; treat EPS/price values as best-effort, not
audited vendor data.  See README "Data quality & limitations".
"""
import io, json, urllib.request, concurrent.futures as cf
from pathlib import Path
import pandas as pd

DATA=Path(__file__).resolve().parent/"data"; DATA.mkdir(exist_ok=True)
UA={"User-Agent":"Mozilla/5.0"}
FINS="https://codeload.github.com/Chinar-byte/FINS3666-Group-Project/tar.gz/refs/heads/main"
MP="https://raw.githubusercontent.com/magiccpp/price_data/master/{t}.csv"
DO="https://raw.githubusercontent.com/do0405/invest-prototype/main/data/us/{t}.csv"

def get(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=timeout) as r:
            return r.read()
    except Exception:
        return None

def build_earnings():
    import tarfile
    raw=get(FINS,180)
    tf=tarfile.open(fileobj=io.BytesIO(raw))
    rows=[]
    for m in tf.getmembers():
        if "earnings_data/" in m.name and m.name.endswith("_earnings.csv"):
            t=m.name.split("/")[-1].replace("_earnings.csv","")
            d=pd.read_csv(tf.extractfile(m)); d.columns=[c.strip() for c in d.columns]
            dc=[c for c in d.columns if "date" in c.lower().replace(" ","")][0]
            dt=pd.to_datetime(d[dc],errors="coerce",utc=True)
            ny=dt.dt.tz_convert("America/New_York")
            for i,r in d.iterrows():
                h=ny.iloc[i].hour if pd.notna(ny.iloc[i]) else None
                sess="unknown" if h is None else ("bmo" if h<=10 else "amc")
                rows.append(dict(ticker=t,ts=str(r[dc]),
                    ann_date=ny.iloc[i].normalize().tz_localize(None) if pd.notna(ny.iloc[i]) else pd.NaT,
                    session=sess, est=pd.to_numeric(r.get("EPS Estimate"),errors="coerce"),
                    act=pd.to_numeric(r.get("Reported EPS"),errors="coerce"),
                    surp=pd.to_numeric(r.get("Surprise(%)"),errors="coerce")))
    e=pd.DataFrame(rows).dropna(subset=["ann_date","surp","est","act"])
    e.to_csv(DATA/"earnings_events.csv",index=False)
    print("earnings_events.csv:",e.shape,"tickers",e.ticker.nunique())
    return sorted(e.ticker.unique())

def norm_price(txt):
    d=pd.read_csv(io.StringIO(txt)); d.columns=[c.strip() for c in d.columns]
    dc="Date" if "Date" in d.columns else "date"
    date=pd.to_datetime(d[dc],utc=True,errors="coerce").dt.tz_localize(None).dt.normalize()
    ac=[c for c in d.columns if c.lower().replace(" ","")=="adjclose"]
    col=ac[0] if ac else ("Close" if "Close" in d.columns else "close")
    return pd.DataFrame({"date":date,"adj":pd.to_numeric(d[col],errors="coerce")}).dropna().drop_duplicates("date")

def build_prices(tickers):
    def one(t):
        parts=[]
        for url in (MP.format(t=t),DO.format(t=t)):
            b=get(url,40)
            if b and (b[:40].find(b"Date")>=0 or b[:40].find(b"date")>=0):
                try: parts.append(norm_price(b.decode("utf-8","replace")))
                except Exception: pass
        if not parts: return t,None
        m=pd.concat(parts).sort_values("date").drop_duplicates("date",keep="first"); m["ticker"]=t
        return t,m
    res=[]
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        for t,m in ex.map(one,tickers+["SPY"]):
            if m is not None and len(m)>50: res.append(m)
    panel=pd.concat(res,ignore_index=True)[["ticker","date","adj"]]
    panel.to_csv(DATA/"prices_panel.csv.gz",index=False,compression="gzip")
    print("prices_panel.csv.gz rows:",len(panel),"tickers",panel.ticker.nunique(),
          panel.date.min().date(),"->",panel.date.max().date())

if __name__=="__main__":
    tk=build_earnings()
    build_prices(tk)
