import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# Setari pagina
st.set_page_config(page_title="Fair Value Calculator", layout="wide")
st.title("📈 Calculator Fair Value")
st.markdown("Aplicație bazată pe date reale (Yahoo Finance) pentru evaluarea acțiunilor prin 4 metode.")

# --- SIDEBAR PENTRU INPUT-URI ---
st.sidebar.header("Parametri de Bază")
ticker_symbol = st.sidebar.text_input("Introdu Ticker-ul (ex: AAPL, MSFT)", value="AAPL").upper()

if ticker_symbol:
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Preluare date factuale necesare
        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        # Acesta este EPS-ul curent (FY / Trailing 12 Months)
        eps_ttm = info.get('trailingEps', 0) 
        beta = info.get('beta', 1.0)
        
        # 1. Calcul WACC automat
        try:
            tnx = yf.Ticker("^TNX").info.get('regularMarketPrice', 4.0) / 100
        except:
            tnx = 0.04
        market_return = 0.10 
        cost_of_equity = tnx + beta * (market_return - tnx)
        
        default_wacc = round(cost_of_equity * 100, 2)
        if default_wacc <= 0 or pd.isna(default_wacc): default_wacc = 8.5
        
        st.sidebar.subheader("Ajustări DCF")
        wacc = st.sidebar.number_input("WACC (%)", value=float(default_wacc), step=0.1) / 100
        terminal_growth = st.sidebar.number_input("Terminal Growth Rate (%)", value=2.5, step=0.1) / 100
        
        st.sidebar.subheader("Ajustări Peter Lynch")
        lynch_period = st.sidebar.radio("Baza de calcul pentru creștere", ["Anual (FY Y/Y)", "Trimestrial (Q/Q YoY)"])

        st.sidebar.subheader("Ajustări Evaluare Relativă")
        sector_pe = st.sidebar.number_input("P/E Mediu Sector", value=15.0, step=0.5)

        st.sidebar.subheader("Ajustări PEG")
        raw_growth = info.get('earningsGrowth')
        est_growth = (raw_growth * 100) if raw_growth is not None else 10.0
        forward_growth = st.sidebar.number_input("Rata de creștere estimată (%)", value=float(est_growth), step=1.0)

        # --- CALCUL METODE ---
        st.header(f"Rezultate pentru {info.get('shortName', ticker_symbol)} ({ticker_symbol})")
        st.write(f"**Preț Curent:** {current_price} USD | **EPS (TTM / FY):** {eps_ttm} USD")
        
        # --- RÂNDUL 1 (Garantează ordinea 1 și 2) ---
        r1_col1, r1_col2 = st.columns(2)
        
        # 1. DISCOUNTED CASH FLOW (DCF)
        with r1_col1:
            st.subheader("1. Discounted Cashflow (DCF)")
            try:
                cashflow = ticker.cashflow
                if 'Free Cash Flow' in cashflow.index:
                    fcf_current = cashflow.loc['Free Cash Flow'].dropna().iloc[0]
                else:
                    ocf = cashflow.loc['Operating Cash Flow'].dropna().iloc[0]
                    capex = cashflow.loc['Capital Expenditure'].dropna().iloc[0]
                    fcf_current = ocf + capex 
                
                shares_out = info.get('sharesOutstanding', 1)
                fcf_per_share = fcf_current / shares_out
                
                fcf_projected = [fcf_per_share * (1 + forward_growth/100)**i for i in range(1, 6)]
                pv_fcf = sum([fcf / ((1 + wacc)**i) for i, fcf in enumerate(fcf_projected, 1)])
                
                terminal_value = (fcf_projected[-1] * (1 + terminal_growth)) / (wacc - terminal_growth)
                pv_tv = terminal_value / ((1 + wacc)**5)
                
                dcf_fair_value = pv_fcf + pv_tv
                st.metric("Fair Value (DCF)", f"{max(0, dcf_fair_value):.2f} USD")
                st.caption(f"Calculat cu WACC: {wacc*100:.2f}%, FCF initial/actiune: {fcf_per_share:.2f} USD")
            except Exception as e:
                st.error("Date insuficiene pentru calculul DCF din YFinance.")
                dcf_fair_value = 0
                
        # 2. METODA PETER LYNCH 
        with r1_col2:
            st.subheader("2. Metoda Peter Lynch")
            try:
                # Căutăm sigur rândul EPS și curățăm datele Nule cu .dropna()
                if lynch_period == "Anual (FY Y/Y)":
                    stmt = ticker.income_stmt
                    eps_rows = [r for r in stmt.index if 'EPS' in str(r) and 'Diluted' in str(r)]
                    if not eps_rows: eps_rows = [r for r in stmt.index if 'EPS' in str(r)]
                    
                    eps_data = stmt.loc[eps_rows[0]].dropna() if eps_rows else []
                    if len(eps_data) >= 2:
                        eps_now = eps_data.iloc[0]
                        eps_prev = eps_data.iloc[1]
                    else:
                        eps_now, eps_prev = None, None
                else: # Trimestrial Q/Q YoY
                    stmt = ticker.quarterly_income_stmt
                    eps_rows = [r for r in stmt.index if 'EPS' in str(r) and 'Diluted' in str(r)]
                    if not eps_rows: eps_rows = [r for r in stmt.index if 'EPS' in str(r)]
                    
                    eps_data = stmt.loc[eps_rows[0]].dropna() if eps_rows else []
                    if len(eps_data) >= 5:
                        eps_now = eps_data.iloc[0] # Trimestrul Curent
                        eps_prev = eps_data.iloc[4] # Același trimestru anul trecut
                    else:
                        eps_now, eps_prev = None, None
                
                if eps_now is None or eps_prev is None:
                    st.warning(f"Yahoo Finance nu a raportat suficiente trimestre consecutive pentru {lynch_period}.")
                    lynch_fair_value = 0
                elif eps_prev <= 0:
                    st.warning("EPS-ul anterior a fost zero sau negativ. Nu se poate calcula matematic procentul.")
                    lynch_fair_value = 0
                else:
                    growth_ratio = (eps_now / eps_prev)
                    growth_percentage = (growth_ratio - 1) * 100
                    
                    # Formula ta: EPS Curent TTM (FY) * Procentul de creștere rezultat
                    lynch_fair_value = eps_ttm * growth_percentage
                    
                    st.metric("Fair Value (Lynch)", f"{max(0, lynch_fair_value):.2f} USD")
                    st.caption(f"Calcul: EPS Curent ({eps_ttm}) * Creșterea {lynch_period} ({growth_percentage:.2f}%)")
            except Exception as e:
                st.error("Date insuficiente în rapoartele financiare.")
                lynch_fair_value = 0

        # --- RÂNDUL 2 (Garantează ordinea 3 și 4) ---
        r2_col1, r2_col2 = st.columns(2)

        # 3. EVALUARE RELATIVĂ
        with r2_col1:
            st.subheader("3. Evaluare Relativă")
            relative_fair_value = eps_ttm * sector_pe
            st.metric("Fair Value (Relativ)", f"{max(0, relative_fair_value):.2f} USD")
            st.caption(f"Calculat ca: EPS ({eps_ttm}) * P/E Sector ({sector_pe})")

        # 4. METODA PEG
        with r2_col2:
            st.subheader("4. Metoda PEG")
            peg_ratio = info.get('pegRatio')
            
            peg_fair_value = eps_ttm * forward_growth
            
            st.metric("Fair Value (PEG = 1)", f"{max(0, peg_fair_value):.2f} USD")
            
            if eps_ttm <= 0:
                st.warning("Compania are EPS negativ sau 0.")
            elif forward_growth <= 0:
                st.warning("Rata de creștere este 0 sau negativă.")
            elif peg_ratio:
                st.caption(f"PEG actual raportat: {peg_ratio}. Fair Value asumat pentru un PEG de 1.0")
            else:
                st.caption("Calculat asertiv pentru un PEG perfect de 1.0.")

        # --- SUMAR SI CONCLUZIE ---
        st.markdown("---")
        st.subheader("💡 Sumar Evaluare")
        
        valid_evals = [v for v in [dcf_fair_value, lynch_fair_value, relative_fair_value, peg_fair_value] if v > 0]
        if valid_evals:
            mediana = np.median(valid_evals)
            delta = mediana - current_price
            
            st.metric("Fair Value Median (Consensul metodelor valide)", 
                      f"{mediana:.2f} USD", 
                      f"{delta:.2f} USD vs Preț Curent",
                      delta_color="normal" if delta > 0 else "inverse")
            
            st.info("Această evaluare folosește strict date financiare raportate și regulile matematice agreate, fără a adăuga speculații de piață.")
            
    except Exception as e:
        st.error("Eroare la preluarea datelor. Verifică dacă ticker-ul este corect.")
