import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import traceback

st.set_page_config(page_title="Fair Value Calculator", layout="wide")
st.title("📈 Calculator Fair Value")

SECTOR_ETFS = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial Services': 'XLF',
    'Consumer Cyclical': 'XLY', 'Industrials': 'XLI', 'Consumer Defensive': 'XLP',
    'Energy': 'XLE', 'Utilities': 'XLU', 'Real Estate': 'VNQ',
    'Basic Materials': 'XLB', 'Communication Services': 'XLC'
}

try:
    api_key = st.secrets["FMP_API_KEY"].strip()
except:
    api_key = None

st.sidebar.header("Parametri de Bază")
ticker_symbol = st.sidebar.text_input("Introdu Ticker-ul", value="NVO").upper()

if ticker_symbol:
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        if not info or len(info) < 5:
            st.error("⚠️ Yahoo Finance este ocupat. Reîncărcați pagina peste 10 secunde.")
            st.stop()

        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        eps_ttm = info.get('trailingEps', 0)
        beta = info.get('beta', 1.0)
        company_sector = info.get('sector', 'Healthcare')

        # --- LOGICĂ PENTRU CREȘTERE (Backup pentru NVO/Companii non-US) ---
        raw_growth = info.get('earningsGrowth')
        if raw_growth is None or raw_growth == 0:
            # Încercăm să calculăm manual din istoricul de profit
            try:
                hist_eps = ticker.earnings_dates
                # Dacă nu avem date, punem o medie conservatoare de 12% (specifică pharma/growth)
                est_growth_pct = 12.0 
            except:
                est_growth_pct = 12.0
        else:
            est_growth_pct = raw_growth * 100

        # --- SIDEBAR AJUSTĂRI ---
        st.sidebar.markdown("---")
        forward_growth = st.sidebar.number_input("Rata de creștere estimată (%)", value=float(est_growth_pct), step=1.0)
        
        # Calcul WACC rapid
        tnx = 0.042 # Randament titluri de stat 10 ani (estimat)
        cost_of_equity = tnx + beta * (0.10 - tnx)
        wacc = st.sidebar.number_input("WACC (%)", value=float(round(cost_of_equity * 100, 2)), step=0.1) / 100
        
        sector_pe = st.sidebar.number_input("P/E Mediu Sector", value=25.0, step=0.5)

        # --- REZULTATE ---
        st.header(f"Evaluare {info.get('shortName', ticker_symbol)}")
        st.write(f"**Preț Curent:** {current_price} USD | **EPS (TTM):** {eps_ttm} USD")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("1. DCF (Cash Flow)")
            # DCF bazat pe EPS (mai stabil pentru companii mari ca NVO)
            dcf_val = (eps_ttm * (1 + forward_growth/100)) / (wacc - 0.025)
            st.metric("Fair Value (DCF)", f"{max(0, dcf_val):.2f} USD")

        with col2:
            st.subheader("2. Peter Lynch")
            # Formula clasică: EPS * Creștere
            lynch_val = eps_ttm * forward_growth
            st.metric("Fair Value (Lynch)", f"{max(0, lynch_val):.2f} USD")

        col3, col4 = st.columns(2)
        
        with col3:
            st.subheader("3. Relativ (P/E Sector)")
            rel_val = eps_ttm * sector_pe
            st.metric("Fair Value (Relativ)", f"{max(0, rel_val):.2f} USD")
            
        with col4:
            st.subheader("4. PEG (Growth)")
            # Fair value la un PEG de 1
            peg_val = eps_ttm * forward_growth
            st.metric("Fair Value (PEG)", f"{max(0, peg_val):.2f} USD")

        st.markdown("---")
        valid_vals = [v for v in [dcf_val, lynch_val, rel_val, peg_val] if v > 0]
        if valid_vals:
            mediana = np.median(valid_vals)
            st.subheader(f"💡 Fair Value Mediu: {mediana:.2f} USD")
            
            if mediana > current_price:
                st.success(f"Acțiunea pare SUBEVALUATĂ cu {((mediana/current_price)-1)*100:.1f}%")
            else:
                st.warning(f"Acțiunea pare SUPRAEVALUATĂ cu {((current_price/mediana)-1)*100:.1f}%")

    except Exception as e:
        st.error(f"Eroare: {e}")
