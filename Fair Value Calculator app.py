import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import traceback

st.set_page_config(page_title="Fair Value Calculator", layout="wide")
st.title("📈 Calculator Fair Value")
st.markdown("Aplicație optimizată cu **Memorie Cache** pentru a preveni blocajele de la Yahoo Finance.")

SECTOR_ETFS = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF',
    'Consumer Cyclical': 'XLY', 'Industrials': 'XLI', 'Consumer Defensive': 'XLP',
    'Energy': 'XLE', 'Utilities': 'XLU', 'Real Estate': 'VNQ',
    'Basic Materials': 'XLB', 'Communication Services': 'XLC'
}

try:
    api_key = st.secrets["FMP_API_KEY"].strip()
except Exception:
    api_key = None

# --- FUNCȚII CU MEMORIE CACHE (Se rulează o singură dată pe oră per Ticker) ---
@st.cache_data(ttl=3600, show_spinner="Se descarcă datele financiare sigure...")
def fetch_financial_data(symbol):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"})
    
    t = yf.Ticker(symbol, session=session)
    info = t.info
    
    if not info or len(info) < 5:
        raise ValueError("Blocaj Yahoo Finance (Rate Limit).")
        
    # Extragem tot ce avem nevoie intr-un dictionar ca sa nu mai interogam YF mai tarziu
    try: tnx = yf.Ticker("^TNX", session=session).info.get('regularMarketPrice', 4.0) / 100
    except: tnx = 0.04
    
    return {
        "info": info,
        "cashflow": t.cashflow,
        "income_stmt": t.income_stmt,
        "q_income_stmt": t.quarterly_income_stmt,
        "tnx": tnx
    }

@st.cache_data(ttl=3600)
def fetch_etf_pe(sector):
    if sector not in SECTOR_ETFS: return 15.0, "Default"
    etf = SECTOR_ETFS[sector]
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        pe = yf.Ticker(etf, session=session).info.get('trailingPE', 15.0)
        return round(pe, 2), etf
    except:
        return 15.0, "Default"

@st.cache_data(ttl=3600)
def fetch_fmp_estimates(symbol, key):
    if not key: return None
    url = f"https://financialmodelingprep.com/api/v3/analyst-estimates/{symbol}?limit=2&apikey={key}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200 and len(resp.json()) > 0:
            return resp.json()[0]
        elif resp.status_code == 403:
            return "LIMITAT"
    except: pass
    return None

# --- SIDEBAR PENTRU INPUT-URI ---
st.sidebar.header("Parametri de Bază")
ticker_symbol = st.sidebar.text_input("Introdu Ticker-ul (ex: AAPL, NVO)", value="AAPL").upper()

if ticker_symbol:
    try:
        # Preluam datele folosind sistemul de Memorie (Cache)
        data = fetch_financial_data(ticker_symbol)
        info = data["info"]
        
        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        eps_ttm = info.get('trailingEps')
        if eps_ttm is None or eps_ttm <= 0:
            eps_ttm = info.get('forwardEps', 0)
            
        beta = info.get('beta', 1.0)
        company_sector = info.get('sector', 'Nespecificat')
        
        # --- PANOU INFORMATIV: ESTIMĂRI ANALIȘTI ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("📊 Estimări Analiști (Consens)")
        
        fmp_data = fetch_fmp_estimates(ticker_symbol, api_key)
        fmp_success = False
        
        if isinstance(fmp_data, dict):
            st.sidebar.success("Date FMP conectate!")
            st.sidebar.write(f"**EPS Estimat:** {fmp_data.get('estimatedEps')} USD")
            if fmp_data.get('estimatedRevenue'):
                st.sidebar.write(f"**Venituri Estimate:** {fmp_data.get('estimatedRevenue'):,.0f} USD")
            fmp_success = True
        elif fmp_data == "LIMITAT":
            st.sidebar.caption("Cont FMP limitat. Folosim date YF.")
        elif api_key:
            st.sidebar.caption("FMP nu are date. Folosim YF.")
        else:
            st.sidebar.caption("Fără cheie FMP. Folosim YF.")

        if not fmp_success:
            forward_eps = info.get('forwardEps')
            if forward_eps and eps_ttm and eps_ttm > 0:
                implied_1y_eps_growth = ((forward_eps / eps_ttm) - 1) * 100
                st.sidebar.write(f"**Creștere EPS (YF):** {implied_1y_eps_growth:.2f}%")
            else:
                st.sidebar.write("**Creștere EPS:** Indisponibil")

        st.sidebar.markdown("---")

        # 1. Calcul WACC automat
        market_return = 0.10 
        cost_of_equity = data["tnx"] + beta * (market_return - data["tnx"])
        default_wacc = round(cost_of_equity * 100, 2)
        if default_wacc <= 0 or pd.isna(default_wacc): default_wacc = 8.5
        
        st.sidebar.subheader("Ajustări DCF")
        wacc = st.sidebar.number_input("WACC (%)", value=float(default_wacc), step=0.1) / 100
        terminal_growth = st.sidebar.number_input("Terminal Growth Rate (%)", value=2.5, step=0.1) / 100
        
        st.sidebar.subheader("Ajustări Peter Lynch")
        lynch_period = st.sidebar.radio("Baza de calcul pentru creștere", ["Anual (FY Y/Y)", "Trimestrial (Q/Q YoY)"])

        st.sidebar.subheader("Ajustări Evaluare Relativă")
        fetched_pe, etf_used = fetch_etf_pe(company_sector)
        
        st.sidebar.write(f"Sector identificat: **{company_sector}**")
        if etf_used != "Default": st.sidebar.caption(f"P/E extras din ETF: {etf_used}")
        else: st.sidebar.caption("Se folosește o medie generală.")
            
        sector_pe = st.sidebar.number_input("P/E Mediu Sector", value=float(fetched_pe), step=0.5)

        st.sidebar.subheader("Ajustări PEG")
        raw_growth = info.get('earningsGrowth')
        est_growth = (raw_growth * 100) if raw_growth is not None else 10.0
        forward_growth = st.sidebar.number_input("Rata de creștere estimată (%)", value=float(est_growth), step=1.0)

        # --- CALCUL METODE ---
        st.header(f"Rezultate pentru {info.get('shortName', ticker_symbol)} ({ticker_symbol})")
        st.write(f"**Preț Curent:** {current_price} USD | **EPS utilizat:** {eps_ttm} USD")
        
        r1_col1, r1_col2 = st.columns(2)
        
        # 1. DISCOUNTED CASH FLOW (DCF)
        with r1_col1:
            st.subheader("1. Discounted Cashflow (DCF)")
            try:
                cf = data["cashflow"]
                if 'Free Cash Flow' in cf.index and not cf.loc['Free Cash Flow'].dropna().empty:
                    fcf_current = cf.loc['Free Cash Flow'].dropna().iloc[0]
                elif 'Operating Cash Flow' in cf.index and 'Capital Expenditure' in cf.index:
                    fcf_current = cf.loc['Operating Cash Flow'].dropna().iloc[0] + cf.loc['Capital Expenditure'].dropna().iloc[0]
                else:
                    raise ValueError("Date FCF lipsă.")
                
                fcf_per_share = fcf_current / info.get('sharesOutstanding', 1)
                fcf_proj = [fcf_per_share * (1 + forward_growth/100)**i for i in range(1, 6)]
                pv_fcf = sum([f / ((1 + wacc)**i) for i, f in enumerate(fcf_proj, 1)])
                tv = (fcf_proj[-1] * (1 + terminal_growth)) / (wacc - terminal_growth)
                pv_tv = tv / ((1 + wacc)**5)
                
                dcf_fair_value = pv_fcf + pv_tv
                st.metric("Fair Value (DCF)", f"{max(0, dcf_fair_value):.2f} USD")
                st.caption(f"Calculat cu WACC: {wacc*100:.2f}%, FCF/acțiune: {fcf_per_share:.2f} USD")
            except Exception as e:
                st.error("Date insuficiente pentru calculul DCF.")
                dcf_fair_value = 0
                
        # 2. METODA PETER LYNCH 
        with r1_col2:
            st.subheader("2. Metoda Peter Lynch")
            try:
                stmt = data["income_stmt"] if lynch_period == "Anual (FY Y/Y)" else data["q_income_stmt"]
                eps_rows = [r for r in stmt.index if 'EPS' in str(r) and 'Diluted' in str(r)]
                if not eps_rows: eps_rows = [r for r in stmt.index if 'EPS' in str(r)]
                
                eps_data = stmt.loc[eps_rows[0]].dropna() if eps_rows else []
                idx_prev = 1 if lynch_period == "Anual (FY Y/Y)" else 4
                
                if len(eps_data) > idx_prev:
                    eps_now, eps_prev = eps_data.iloc[0], eps_data.iloc[idx_prev]
                else:
                    eps_now, eps_prev = None, None
                
                if eps_now is None or eps_prev is None:
                    st.warning(f"Trimestre consecutive lipsă pentru {lynch_period}.")
                    lynch_fair_value = 0
                elif eps_prev <= 0:
                    st.warning("EPS-ul anterior zero sau negativ. Calcul imposibil.")
                    lynch_fair_value = 0
                else:
                    growth_ratio = (eps_now / eps_prev)
                    growth_percentage = (growth_ratio - 1) * 100
                    lynch_fair_value = eps_ttm * growth_percentage
                    st.metric("Fair Value (Lynch)", f"{max(0, lynch_fair_value):.2f} USD")
                    st.caption(f"Calcul: EPS ({eps_ttm}) * Creșterea {lynch_period} ({growth_percentage:.2f}%)")
                
                # --- AXA VIZUALĂ ---
                if eps_ttm > 0:
                    current_pe = current_price / eps_ttm
                    if current_pe <= 15: interpretare, col = "Subevaluat", "#4CAF50"
                    elif current_pe < 20: interpretare, col = "Ușor subevaluat", "#8BC34A"
                    elif current_pe == 20: interpretare, col = "Fair value", "#FFC107"
                    elif current_pe < 25: interpretare, col = "Ușor supraevaluat", "#FF9800"
                    else: interpretare, col = "Supraevaluat", "#F44336"
                        
                    if current_pe <= 15: pos = (current_pe / 15) * 30
                    elif current_pe <= 20: pos = 30 + ((current_pe - 15) / 5) * 20
                    elif current_pe <= 25: pos = 50 + ((current_pe - 20) / 5) * 20
                    else: pos = 70 + min(((current_pe - 25) / 15) * 30, 30) 
                    
                    html_content = f"""<div style="margin-top: 15px; margin-bottom: 30px; padding: 15px; background-color: rgba(128,128,128,0.1); border-radius: 8px;">
    <div style="font-size: 14px; margin-bottom: 15px;">📊 <b>P/E Curent: {current_pe:.1f}</b> (<span style="color: {col}; font-weight: bold;">{interpretare}</span>)</div>
    <div style="position: relative; width: 100%; height: 12px; background: linear-gradient(to right, #4CAF50 30%, #8BC34A 30% 50%, #FFC107 50% 70%, #F44336 70%); border-radius: 6px;">
        <div style="position: absolute; left: 30%; top: -4px; bottom: -4px; width: 2px; background-color: white; opacity: 0.7;"></div>
        <div style="position: absolute; left: 50%; top: -4px; bottom: -4px; width: 2px; background-color: white; opacity: 0.7;"></div>
        <div style="position: absolute; left: 70%; top: -4px; bottom: -4px; width: 2px; background-color: white; opacity: 0.7;"></div>
        <div style="position: absolute; left: {pos}%; top: -6px; width: 4px; height: 24px; background-color: white; border: 2px solid #333; transform: translateX(-50%); border-radius: 2px;"></div>
    </div>
    <div style="position: relative; width: 100%; height: 15px; margin-top: 8px; font-size: 12px; font-weight: bold; color: gray;">
        <span style="position: absolute; left: 30%; transform: translateX(-50%);">15</span>
        <span style="position: absolute; left: 50%; transform: translateX(-50%);">20</span>
        <span style="position: absolute; left: 70%; transform: translateX(-50%);">25+</span>
    </div>
</div>"""
                    st.markdown(html_content, unsafe_allow_html=True)
            except Exception as e:
                st.error("Date insuficiente în rapoarte.")
                lynch_fair_value = 0

        r2_col1, r2_col2 = st.columns(2)

        # 3. RELATIV
        with r2_col1:
            st.subheader("3. Evaluare Relativă")
            relative_fair_value = eps_ttm * sector_pe
            st.metric("Fair Value (Relativ)", f"{max(0, relative_fair_value):.2f} USD")
            st.caption(f"Calculat ca: EPS ({eps_ttm}) * P/E Sector ({sector_pe})")

        # 4. PEG
        with r2_col2:
            st.subheader("4. Metoda PEG")
            peg_ratio = info.get('pegRatio')
            peg_fair_value = eps_ttm * forward_growth
            st.metric("Fair Value (PEG = 1)", f"{max(0, peg_fair_value):.2f} USD")
            if peg_ratio:
                st.caption(f"PEG actual: {peg_ratio}. Fair Value asumat pentru PEG 1.0")

        # --- SUMAR ---
        st.markdown("---")
        st.subheader("💡 Sumar Evaluare")
        
        valid_evals = [v for v in [dcf_fair_value, lynch_fair_value, relative_fair_value, peg_fair_value] if v > 0]
        if valid_evals:
            mediana = np.median(valid_evals)
            delta = mediana - current_price
            
            st.metric("Fair Value Median (Consens)", 
                      f"{mediana:.2f} USD", 
                      f"{delta:.2f} USD vs Preț Curent",
                      delta_color="normal" if delta > 0 else "inverse")
            
    except Exception as e:
        st.error(f"❌ Eroare la citirea datelor. Din cauza reîncărcărilor repetate, IP-ul a fost restricționat temporar. Te rog să aștepți 5 minute și să reîncarci pagina.")
        with st.expander("Detalii depanare"):
            st.code(traceback.format_exc())
