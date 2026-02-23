import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import traceback

# Setari pagina
st.set_page_config(page_title="Fair Value Calculator", layout="wide")
st.title("📈 Calculator Fair Value")
st.markdown("Aplicație bazată pe date reale pentru evaluarea acțiunilor prin 4 metode.")

SECTOR_ETFS = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF',
    'Consumer Cyclical': 'XLY', 'Industrials': 'XLI', 'Consumer Defensive': 'XLP',
    'Energy': 'XLE', 'Utilities': 'XLU', 'Real Estate': 'VNQ',
    'Basic Materials': 'XLB', 'Communication Services': 'XLC'
}

# Incarcare API Key din Streamlit Secrets
try:
    api_key = st.secrets["FMP_API_KEY"].strip()
except Exception as e:
    api_key = None

# --- SIDEBAR PENTRU INPUT-URI ---
st.sidebar.header("Parametri de Bază")
ticker_symbol = st.sidebar.text_input("Introdu Ticker-ul (ex: AAPL, MSFT)", value="AAPL").upper()

if ticker_symbol:
    try:
        # Preluare date de baza
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Daca info e gol, inseamna ca Yahoo Finance ne-a blocat
        if not info or len(info) < 5:
            st.error("⚠️ Yahoo Finance refuză conexiunea temporar. Încearcă peste câteva minute.")
            st.stop()

        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        eps_ttm = info.get('trailingEps', 0) 
        beta = info.get('beta', 1.0)
        company_sector = info.get('sector', 'Nespecificat')
        
        # --- PANOU INFORMATIV: ESTIMĂRI ANALIȘTI ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("📊 Estimări Analiști (Consens)")
        
        if api_key:
            try:
                url = f"https://financialmodelingprep.com/api/v3/analyst-estimates/{ticker_symbol}?limit=2&apikey={api_key}"
                response = requests.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if len(data) > 0:
                        est_eps_current = data[0].get('estimatedEps')
                        st.sidebar.success("Date FMP conectate!")
                        st.sidebar.write(f"**EPS Estimat:** {est_eps_current} USD")
                elif response.status_code == 403:
                    st.sidebar.warning("Cont FMP Gratuit: Acces limitat la estimări.")
            except:
                st.sidebar.error("Eroare conexiune FMP.")
        else:
            st.sidebar.error("⚠️ Cheia API lipsește din Secrets.")

        st.sidebar.markdown("---")

        # 1. Calcul WACC automat
        try:
            tnx = yf.Ticker("^TNX").info.get('regularMarketPrice', 4.0) / 100
        except:
            tnx = 0.04
        market_return = 0.10 
        cost_of_equity = tnx + beta * (market_return - tnx)
        wacc = st.sidebar.number_input("WACC (%)", value=float(round(cost_of_equity * 100, 2)), step=0.1) / 100
        terminal_growth = st.sidebar.number_input("Terminal Growth (%)", value=2.5, step=0.1) / 100
        
        st.sidebar.subheader("Ajustări Peter Lynch")
        lynch_period = st.sidebar.radio("Baza creștere", ["Anual (FY Y/Y)", "Trimestrial (Q/Q YoY)"])

        # Evaluare Relativa
        fetched_pe = 15.0
        if company_sector in SECTOR_ETFS:
            try:
                etf_info = yf.Ticker(SECTOR_ETFS[company_sector]).info
                fetched_pe = etf_info.get('trailingPE', 15.0)
            except: pass
        sector_pe = st.sidebar.number_input("P/E Mediu Sector", value=float(fetched_pe), step=0.5)

        # PEG
        est_growth = (info.get('earningsGrowth', 0.1) * 100)
        forward_growth = st.sidebar.number_input("Creștere estimată (%)", value=float(est_growth), step=1.0)

        # --- REZULTATE ---
        st.header(f"Rezultate pentru {info.get('shortName', ticker_symbol)}")
        st.write(f"**Preț Curent:** {current_price} USD | **EPS:** {eps_ttm} USD")
        
        col1, col2 = st.columns(2)
        
        # 1. DCF
        with col1:
            st.subheader("1. DCF")
            try:
                cf = ticker.cashflow
                fcf = cf.loc['Free Cash Flow'].iloc[0] if 'Free Cash Flow' in cf.index else 0
                fcf_share = fcf / info.get('sharesOutstanding', 1)
                dcf_val = (fcf_share * (1 + forward_growth/100)) / (wacc - terminal_growth/100)
                st.metric("Fair Value (DCF)", f"{max(0, dcf_val):.2f} USD")
            except:
                st.write("Date DCF indisponibile.")
                dcf_val = 0

        # 2. Lynch
        with col2:
            st.subheader("2. Peter Lynch")
            growth = forward_growth # simplificat pentru diagnostic
            lynch_val = eps_ttm * growth
            st.metric("Fair Value (Lynch)", f"{max(0, lynch_val):.2f} USD")

        col3, col4 = st.columns(2)
        # 3. Relativ
        with col3:
            st.subheader("3. Relativ")
            rel_val = eps_ttm * sector_pe
            st.metric("Fair Value (Relativ)", f"{max(0, rel_val):.2f} USD")
        # 4. PEG
        with col4:
            st.subheader("4. PEG")
            peg_val = eps_ttm * forward_growth
            st.metric("Fair Value (PEG)", f"{max(0, peg_val):.2f} USD")

    except Exception as e:
        st.error(f"❌ Eroare tehnică detectată: {e}")
        with st.expander("Vezi detalii pentru depanare"):
            st.code(traceback.format_exc())
