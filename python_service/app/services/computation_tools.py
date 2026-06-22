"""
Computation Tools — Deterministic calculation skills for AI analysts.

These are executable tools that perform exact calculations, eliminating
the need for LLMs to do arithmetic (which they're bad at).

Tools:
  - dcf_calculator: Full DCF valuation with sensitivity table
  - position_sizer: Fixed-fractional position sizing
  - kelly_calculator: Kelly Criterion optimal position %
  - beat_miss_scorer: Quantify earnings beat/miss
  - comps_valuation: Derive fair value from peer multiples
  - pillar_scorer: Score thesis health from pillar statuses
"""

import math
from typing import Dict, List, Any, Optional


def dcf_calculate(params: Dict[str, Any]) -> str:
    """
    Full DCF calculation with sensitivity table.
    
    Required params:
      - fcf_base: Current year FCF (in millions)
      - growth_rates: List of 5 growth rates for years 1-5 (e.g. [0.15, 0.12, 0.10, 0.08, 0.06])
      - terminal_growth: Perpetual growth rate (e.g. 0.03)
      - wacc: Weighted average cost of capital (e.g. 0.09)
      - shares_outstanding: In millions
      - net_debt: Net debt in millions (debt - cash). Positive = debt, Negative = net cash
    
    Optional:
      - currency: "USD" / "CNY" / "HKD" (default "USD")
    """
    try:
        fcf_base = float(params.get("fcf_base", 0))
        growth_rates = params.get("growth_rates", [0.10, 0.08, 0.07, 0.06, 0.05])
        terminal_growth = float(params.get("terminal_growth", 0.03))
        
        # Force-override LLM hallucinations for critical WACC parameters (Phase 4 Security/DCF fix)
        try:
            import yfinance as yf
            # Try to get 10-year treasury yield for risk-free rate
            tnx = yf.Ticker("^TNX")
            hist = tnx.history(period="1d")
            if not hist.empty:
                real_rf = float(hist["Close"].iloc[-1]) / 100.0
            else:
                real_rf = 0.042  # fallback 4.2%
        except Exception:
            real_rf = 0.042

        # Override RF and ERP with robust defaults instead of trusting the LLM
        rf = real_rf
        erp = 0.055  # Standard ERP
        beta = float(params.get("beta", 1.0)) # We could try fetching beta from yf here as well
        
        try:
            symbol = params.get("symbol", "")
            if symbol:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                if "beta" in info and info["beta"]:
                    beta = float(info["beta"])
        except Exception:
            pass

        kd = params.get("kd")
        tax_rate = float(params.get("tax_rate", 0.25))
        debt_weight = float(params.get("debt_weight", 0.3))
        equity_weight = 1.0 - debt_weight
        
        wacc_breakdown = ""
        ke = float(rf) + float(beta) * float(erp)
        if kd is not None:
            wacc = equity_weight * ke + debt_weight * float(kd) * (1.0 - tax_rate)
            wacc_breakdown = f" (Breakdown (SYSTEM OVERRIDE): Ke={ke:.2%}, Kd={float(kd):.2%}, Wd={debt_weight:.0%}, Tax={tax_rate:.0%}, Real_Rf={float(rf):.2%}, Real_Beta={float(beta):.2f}, ERP={float(erp):.2%})"
        else:
            wacc = ke
            wacc_breakdown = f" (Breakdown (SYSTEM OVERRIDE): 100% Equity, CAPM Ke={ke:.2%}, Real_Rf={float(rf):.2%}, Real_Beta={float(beta):.2f}, ERP={float(erp):.2%})"

        shares = float(params.get("shares_outstanding", 1))
        net_debt = float(params.get("net_debt", 0))
        currency = params.get("currency", "USD")

        # Sanity Checks on CAPM inputs, WACC, and terminal growth
        if rf is not None:
            rf_val = float(rf)
            if rf_val < 0.01 or rf_val > 0.15:
                return _obs("DCF ERROR: Unreasonable risk-free rate: {:.2%}. Must be between 1% and 15%.".format(rf_val))
        if beta is not None:
            beta_val = float(beta)
            if beta_val < 0.0 or beta_val > 3.0:
                return _obs("DCF ERROR: Unreasonable beta: {}. Must be between 0.0 and 3.0.".format(beta_val))
        if erp is not None:
            erp_val = float(erp)
            if erp_val < 0.02 or erp_val > 0.12:
                return _obs("DCF ERROR: Unreasonable Equity Risk Premium: {:.2%}. Must be between 2% and 12%.".format(erp_val))
        if wacc < 0.02 or wacc > 0.25:
            return _obs("DCF ERROR: Unreasonable WACC: {:.2%}. Must be between 2% and 25%.".format(wacc))
        if terminal_growth < 0.0 or terminal_growth > 0.08:
            return _obs("DCF ERROR: Unreasonable terminal growth rate: {:.2%}. Must be between 0% and 8%.".format(terminal_growth))

        if wacc <= terminal_growth:
            return _obs("DCF ERROR: WACC ({:.2%}) must be > terminal growth ({:.2%}). Model invalid.".format(wacc, terminal_growth))
        if fcf_base <= 0:
            return _obs(f"DCF ERROR: FCF base must be positive. Got: {fcf_base}")

        # Step 1: Project FCFs
        fcfs = []
        current_fcf = fcf_base
        for i, g in enumerate(growth_rates[:5]):
            current_fcf = current_fcf * (1 + g)
            fcfs.append(current_fcf)

        # Pad to 5 years if fewer growth rates provided
        while len(fcfs) < 5:
            fcfs.append(fcfs[-1] * (1 + growth_rates[-1]))

        # Step 2: Terminal value
        terminal_value = fcfs[-1] * (1 + terminal_growth) / (wacc - terminal_growth)

        # Step 3: Discount to present value
        pv_fcfs = [fcf / (1 + wacc) ** (i + 1) for i, fcf in enumerate(fcfs)]
        pv_terminal = terminal_value / (1 + wacc) ** 5

        # Step 4: Enterprise value → Equity value → Per-share
        enterprise_value = sum(pv_fcfs) + pv_terminal
        equity_value = enterprise_value - net_debt
        per_share = equity_value / shares if shares > 0 else 0

        # Step 5: Sensitivity table (WACC ±1%, g ±0.5%)
        sensitivity = []
        for dg in [-0.005, 0, 0.005]:
            row = []
            for dw in [-0.01, 0, 0.01]:
                w = wacc + dw
                g = terminal_growth + dg
                if w <= g:
                    row.append("N/A")
                else:
                    tv = fcfs[-1] * (1 + g) / (w - g)
                    ev = sum(f / (1 + w) ** (i + 1) for i, f in enumerate(fcfs)) + tv / (1 + w) ** 5
                    eq = ev - net_debt
                    row.append(f"{currency} {eq / shares:.2f}")
            sensitivity.append(row)

        # Format output
        lines = []
        lines.append("## DCF Valuation Result (Computed)")
        lines.append("")
        lines.append("### FCF Projections")
        lines.append("| Year | FCF (M) | Growth | PV (M) |")
        lines.append("|------|---------|--------|--------|")
        for i in range(5):
            g = growth_rates[i] if i < len(growth_rates) else growth_rates[-1]
            lines.append(f"| Y{i+1} | {fcfs[i]:,.1f} | {g:.1%} | {pv_fcfs[i]:,.1f} |")
        lines.append("")
        lines.append(f"### Terminal Value: {currency} {terminal_value:,.0f}M (PV: {currency} {pv_terminal:,.0f}M)")
        lines.append(f"### Enterprise Value: {currency} {enterprise_value:,.0f}M")
        lines.append(f"### Net Debt: {currency} {net_debt:,.0f}M")
        lines.append(f"### Equity Value: {currency} {equity_value:,.0f}M")
        lines.append(f"### **Intrinsic Value Per Share: {currency} {per_share:.2f}**")
        lines.append("")
        lines.append("### Sensitivity Table (per-share value)")
        lines.append(f"|  | WACC {wacc-0.01:.1%} | WACC {wacc:.1%} | WACC {wacc+0.01:.1%} |")
        lines.append("|------|------|------|------|")
        labels = [f"g={terminal_growth-0.005:.2%}", f"g={terminal_growth:.2%}", f"g={terminal_growth+0.005:.2%}"]
        for i, (label, row) in enumerate(zip(labels, sensitivity)):
            lines.append(f"| {label} | {row[0]} | {row[1]} | {row[2]} |")
        lines.append("")
        lines.append(f"**Assumptions**: WACC={wacc:.2%}{wacc_breakdown}, Terminal g={terminal_growth:.2%}, Shares={shares:.1f}M")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"DCF Calculation Error: {str(e)}")


def position_size_calculate(params: Dict[str, Any]) -> str:
    """
    Fixed-fractional position sizing.
    
    Required params:
      - account_size: Total portfolio value
      - entry_price: Planned entry price
      - stop_price: Stop-loss price
      - risk_pct: Risk per trade as % (default 1.0)
    
    Optional:
      - currency: "USD" / "CNY" / "HKD"
      - max_position_pct: Max single position % (default 10)
      - portfolio_heat_limit: Max total risk % (default 6)
      - current_heat: Current portfolio risk % (default 0)
    """
    try:
        account = float(params.get("account_size", 100000))
        entry = float(params.get("entry_price", 0))
        stop = float(params.get("stop_price", 0))
        risk_pct = float(params.get("risk_pct", 1.0))
        currency = params.get("currency", "USD")
        max_pos_pct = float(params.get("max_position_pct", 10))
        heat_limit = float(params.get("portfolio_heat_limit", 6))
        current_heat = float(params.get("current_heat", 0))

        if entry <= 0 or stop <= 0:
            return _obs("Position Size ERROR: entry_price and stop_price must be > 0")
        if entry == stop:
            return _obs("Position Size ERROR: entry_price cannot equal stop_price")

        risk_per_share = abs(entry - stop)
        risk_amount = account * (risk_pct / 100)
        shares = math.floor(risk_amount / risk_per_share)
        position_value = shares * entry
        position_pct = (position_value / account) * 100

        # Constraint checks
        warnings = []
        if position_pct > max_pos_pct:
            max_shares = math.floor(account * max_pos_pct / 100 / entry)
            warnings.append(f"⚠️ Position {position_pct:.1f}% exceeds {max_pos_pct}% limit → capped to {max_shares} shares ({currency} {max_shares * entry:,.0f})")
            shares = max_shares
            position_value = shares * entry
            position_pct = (position_value / account) * 100

        new_heat = current_heat + risk_pct
        if new_heat > heat_limit:
            warnings.append(f"⚠️ Portfolio heat would be {new_heat:.1f}% (limit: {heat_limit}%). Consider smaller size.")

        direction = "Long" if entry > stop else "Short"
        r_multiple_1r = risk_per_share
        target_2r = entry + 2 * r_multiple_1r if direction == "Long" else entry - 2 * r_multiple_1r
        target_3r = entry + 3 * r_multiple_1r if direction == "Long" else entry - 3 * r_multiple_1r

        lines = []
        lines.append("## Position Sizing Result (Computed)")
        lines.append("")
        lines.append("| Parameter | Value |")
        lines.append("|-----------|-------|")
        lines.append(f"| Account Size | {currency} {account:,.0f} |")
        lines.append(f"| Direction | {direction} |")
        lines.append(f"| Entry Price | {currency} {entry:.2f} |")
        lines.append(f"| Stop Loss | {currency} {stop:.2f} |")
        lines.append(f"| Risk per Share | {currency} {risk_per_share:.2f} |")
        lines.append(f"| Risk % | {risk_pct:.1f}% |")
        lines.append(f"| Risk Amount | {currency} {risk_amount:,.0f} |")
        lines.append(f"| **Shares** | **{shares}** |")
        lines.append(f"| Position Value | {currency} {position_value:,.0f} |")
        lines.append(f"| Position % | {position_pct:.1f}% |")
        lines.append(f"| Portfolio Heat (after) | {new_heat:.1f}% / {heat_limit}% |")
        lines.append("")
        lines.append("### R-Multiple Targets")
        lines.append(f"| Target | Price | Profit |")
        lines.append(f"|--------|-------|--------|")
        lines.append(f"| 1R (break-even risk) | {currency} {entry + r_multiple_1r if direction == 'Long' else entry - r_multiple_1r:.2f} | {currency} {r_multiple_1r * shares:,.0f} |")
        lines.append(f"| 2R | {currency} {target_2r:.2f} | {currency} {2 * r_multiple_1r * shares:,.0f} |")
        lines.append(f"| 3R | {currency} {target_3r:.2f} | {currency} {3 * r_multiple_1r * shares:,.0f} |")
        if warnings:
            lines.append("")
            lines.append("### ⚠️ Constraint Warnings")
            for w in warnings:
                lines.append(f"- {w}")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Position Sizing Error: {str(e)}")


def kelly_calculate(params: Dict[str, Any]) -> str:
    """
    Kelly Criterion optimal position sizing.
    
    Required params:
      - win_rate: Probability of winning (0-1, e.g. 0.55)
      - avg_win: Average win amount or ratio (e.g. 1.5)
      - avg_loss: Average loss amount or ratio (e.g. 1.0)
    
    Optional:
      - fraction: Kelly fraction to use (default 0.5 = half-Kelly)
    """
    try:
        p = float(params.get("win_rate", 0.5))
        w = float(params.get("avg_win", 1.5))
        l = float(params.get("avg_loss", 1.0))
        fraction = float(params.get("fraction", 0.5))

        if not (0 < p < 1):
            return _obs("Kelly ERROR: win_rate must be between 0 and 1")
        if w <= 0 or l <= 0:
            return _obs("Kelly ERROR: avg_win and avg_loss must be > 0")

        q = 1 - p
        b = w / l  # odds ratio
        
        # Kelly formula: f* = (bp - q) / b
        full_kelly = (b * p - q) / b
        adjusted_kelly = full_kelly * fraction

        # Expected value per bet
        ev = p * w - q * l

        # Edge (expected return per $ risked)
        edge = ev / l

        lines = []
        lines.append("## Kelly Criterion Result (Computed)")
        lines.append("")
        lines.append("| Parameter | Value |")
        lines.append("|-----------|-------|")
        lines.append(f"| Win Rate (p) | {p:.1%} |")
        lines.append(f"| Average Win | {w:.2f} |")
        lines.append(f"| Average Loss | {l:.2f} |")
        lines.append(f"| Odds Ratio (b=W/L) | {b:.2f} |")
        lines.append(f"| Expected Value/Trade | {ev:.3f} |")
        lines.append(f"| Edge (EV/Loss) | {edge:.1%} |")
        lines.append(f"| **Full Kelly f*** | **{full_kelly:.1%}** |")
        lines.append(f"| **{fraction:.0%} Kelly (recommended)** | **{adjusted_kelly:.1%}** |")
        lines.append("")
        
        if full_kelly <= 0:
            lines.append("### ❌ NEGATIVE EDGE — DO NOT TRADE")
            lines.append("Kelly criterion is ≤ 0, meaning this trade has negative expected value.")
        else:
            lines.append("### Interpretation")
            if adjusted_kelly > 0.25:
                lines.append(f"- {fraction:.0%} Kelly = {adjusted_kelly:.1%} — Very large position. High conviction required.")
            elif adjusted_kelly > 0.15:
                lines.append(f"- {fraction:.0%} Kelly = {adjusted_kelly:.1%} — Standard position size.")
            else:
                lines.append(f"- {fraction:.0%} Kelly = {adjusted_kelly:.1%} — Small edge, small position.")
            lines.append(f"- Never exceed Full Kelly ({full_kelly:.1%}) — risk of ruin increases dramatically.")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Kelly Calculation Error: {str(e)}")


def beat_miss_score(params: Dict[str, Any]) -> str:
    """
    Score earnings beat/miss quantitatively.
    
    Required params:
      - metrics: List of dicts, each with:
          - name: Metric name (e.g. "Revenue", "EPS")
          - consensus: Market consensus estimate
          - actual: Actual reported value
          - significance: "high" / "medium" / "low"
    
    Optional:
      - guidance_consensus: Expected guidance
      - guidance_actual: Actual guidance given
    """
    try:
        metrics = params.get("metrics", [])
        if not metrics:
            return _obs("Beat/Miss ERROR: 'metrics' list is required")

        lines = []
        lines.append("## Earnings Beat/Miss Scorecard (Computed)")
        lines.append("")
        lines.append("| Metric | Consensus | Actual | Result | Magnitude | Significance | Score |")
        lines.append("|--------|-----------|--------|--------|-----------|--------------|-------|")

        total_score = 0
        total_weight = 0

        for m in metrics:
            name = m.get("name", "")
            consensus = float(m.get("consensus", 0))
            actual = float(m.get("actual", 0))
            sig = m.get("significance", "medium")

            weight = {"high": 3, "medium": 2, "low": 1}.get(sig, 2)
            
            if consensus != 0:
                magnitude_pct = ((actual - consensus) / abs(consensus)) * 100
            else:
                magnitude_pct = 0

            if magnitude_pct > 0:
                result = "✅ Beat"
                score = min(magnitude_pct * 10, 100)  # cap at 100
            elif magnitude_pct < 0:
                result = "❌ Miss"
                score = max(magnitude_pct * 10, -100)
            else:
                result = "➖ In-line"
                score = 0

            total_score += score * weight
            total_weight += weight

            lines.append(f"| {name} | {consensus:,.2f} | {actual:,.2f} | {result} | {magnitude_pct:+.1f}% | {sig} | {score:+.0f} |")

        # Guidance
        guidance_c = params.get("guidance_consensus")
        guidance_a = params.get("guidance_actual")
        if guidance_c is not None and guidance_a is not None:
            gc = float(guidance_c)
            ga = float(guidance_a)
            if gc != 0:
                g_mag = ((ga - gc) / abs(gc)) * 100
            else:
                g_mag = 0
            g_result = "✅ Above" if g_mag > 0 else "❌ Below" if g_mag < 0 else "➖ In-line"
            g_score = min(g_mag * 15, 100) if g_mag > 0 else max(g_mag * 15, -100)
            total_score += g_score * 4  # highest weight
            total_weight += 4
            lines.append(f"| **Guidance** | {gc:,.2f} | {ga:,.2f} | {g_result} | {g_mag:+.1f}% | **critical** | {g_score:+.0f} |")

        # Composite
        composite = total_score / total_weight if total_weight > 0 else 0
        lines.append("")
        lines.append(f"### Composite Score: **{composite:+.1f}** / 100")
        lines.append("")
        if composite > 50:
            lines.append("**Verdict**: Strong Beat — expect positive estimate revisions")
        elif composite > 20:
            lines.append("**Verdict**: Moderate Beat — mixed but positive overall")
        elif composite > -20:
            lines.append("**Verdict**: In-line — limited price impact expected")
        elif composite > -50:
            lines.append("**Verdict**: Moderate Miss — expect negative estimate revisions")
        else:
            lines.append("**Verdict**: Significant Miss — expect material downside")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Beat/Miss Scoring Error: {str(e)}")


def comps_valuation(params: Dict[str, Any]) -> str:
    """
    Derive fair value range from peer multiples.
    
    Required params:
      - target: Dict with target company metrics:
          - symbol, pe, pb, ps, ev_ebitda, revenue_growth, roe, earnings (for PE method)
          - revenue (for PS method), ebitda (for EV/EBITDA method)
          - shares_outstanding
      - peers: List of dicts, each with:
          - symbol, pe, pb, ps, ev_ebitda, revenue_growth, roe
    """
    try:
        target = params.get("target", {})
        peers = params.get("peers", [])
        if not peers:
            return _obs("Comps ERROR: 'peers' list is required")

        # Calculate medians
        def median(values):
            v = sorted([x for x in values if x and x > 0])
            if not v:
                return None
            n = len(v)
            return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

        peer_pe = median([p.get("pe") for p in peers])
        peer_pb = median([p.get("pb") for p in peers])
        peer_ps = median([p.get("ps") for p in peers])
        peer_ev_ebitda = median([p.get("ev_ebitda") for p in peers])

        target_pe = target.get("pe")
        target_earnings = target.get("earnings")
        target_revenue = target.get("revenue")
        target_ebitda = target.get("ebitda")
        target_book = target.get("book_value")
        shares = target.get("shares_outstanding", 1)
        current_price = target.get("current_price", 0)

        lines = []
        lines.append("## Comps-Based Valuation (Computed)")
        lines.append("")
        lines.append("### Peer Median Multiples")
        lines.append("| Multiple | Peer Median | Target Current | Premium/Discount |")
        lines.append("|----------|-------------|----------------|------------------|")
        
        if peer_pe and target_pe:
            prem = ((target_pe / peer_pe) - 1) * 100
            lines.append(f"| PE | {peer_pe:.1f}x | {target_pe:.1f}x | {prem:+.1f}% |")
        if peer_pb and target.get("pb"):
            prem = ((target.get("pb") / peer_pb) - 1) * 100
            lines.append(f"| PB | {peer_pb:.2f}x | {target.get('pb'):.2f}x | {prem:+.1f}% |")
        if peer_ps and target.get("ps"):
            prem = ((target.get("ps") / peer_ps) - 1) * 100
            lines.append(f"| PS | {peer_ps:.1f}x | {target.get('ps'):.1f}x | {prem:+.1f}% |")
        if peer_ev_ebitda and target.get("ev_ebitda"):
            prem = ((target.get("ev_ebitda") / peer_ev_ebitda) - 1) * 100
            lines.append(f"| EV/EBITDA | {peer_ev_ebitda:.1f}x | {target.get('ev_ebitda'):.1f}x | {prem:+.1f}% |")

        lines.append("")
        lines.append("### Implied Fair Value (per share)")
        lines.append("| Method | Implied Price | vs Current | Upside/Downside |")
        lines.append("|--------|---------------|------------|-----------------|")

        implied_prices = []
        if peer_pe and target_earnings and shares:
            implied = peer_pe * target_earnings / shares
            implied_prices.append(implied)
            upside = ((implied / current_price) - 1) * 100 if current_price else 0
            lines.append(f"| PE-based | {implied:.2f} | {current_price:.2f} | {upside:+.1f}% |")
        if peer_ps and target_revenue and shares:
            implied = peer_ps * target_revenue / shares
            implied_prices.append(implied)
            upside = ((implied / current_price) - 1) * 100 if current_price else 0
            lines.append(f"| PS-based | {implied:.2f} | {current_price:.2f} | {upside:+.1f}% |")
        if peer_ev_ebitda and target_ebitda and shares:
            implied = peer_ev_ebitda * target_ebitda / shares
            implied_prices.append(implied)
            upside = ((implied / current_price) - 1) * 100 if current_price else 0
            lines.append(f"| EV/EBITDA-based | {implied:.2f} | {current_price:.2f} | {upside:+.1f}% |")

        if implied_prices:
            avg_implied = sum(implied_prices) / len(implied_prices)
            low = min(implied_prices)
            high = max(implied_prices)
            lines.append("")
            lines.append(f"### **Comps Fair Value Range: {low:.2f} — {high:.2f} (avg: {avg_implied:.2f})**")
            if current_price:
                avg_upside = ((avg_implied / current_price) - 1) * 100
                lines.append(f"### **Average Implied Upside: {avg_upside:+.1f}%**")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Comps Valuation Error: {str(e)}")


def pillar_score(params: Dict[str, Any]) -> str:
    """
    Score thesis health from pillar statuses.
    
    Required params:
      - pillars: List of dicts, each with:
          - name: Pillar description
          - status: "on_track" / "mixed" / "broken"
          - weight: Importance weight (0-100, will be normalized)
          - evidence: Brief evidence summary
    
    Optional:
      - kill_switches: List of pillar names where "broken" = auto-exit
    """
    try:
        pillars = params.get("pillars", [])
        kill_switches = params.get("kill_switches", [])
        
        if not pillars:
            return _obs("Pillar Score ERROR: 'pillars' list is required")

        status_scores = {"on_track": 100, "mixed": 50, "broken": 0}
        total_weight = sum(p.get("weight", 20) for p in pillars)
        
        lines = []
        lines.append("## Thesis Pillar Scorecard (Computed)")
        lines.append("")
        lines.append("| # | Pillar | Status | Score | Weight | Weighted |")
        lines.append("|---|--------|--------|-------|--------|----------|")

        weighted_sum = 0
        kill_triggered = False

        for i, p in enumerate(pillars, 1):
            name = p.get("name", f"Pillar {i}")
            status = p.get("status", "mixed").lower()
            weight = p.get("weight", 20)
            evidence = p.get("evidence", "")
            
            score = status_scores.get(status, 50)
            norm_weight = weight / total_weight if total_weight > 0 else 1 / len(pillars)
            weighted = score * norm_weight
            weighted_sum += weighted

            icon = {"on_track": "✅", "mixed": "⚠️", "broken": "❌"}.get(status, "❓")
            is_kill = name in kill_switches and status == "broken"
            kill_mark = " 💀" if is_kill else ""
            if is_kill:
                kill_triggered = True

            lines.append(f"| {i} | {name}{kill_mark} | {icon} {status} | {score} | {norm_weight:.0%} | {weighted:.1f} |")

        lines.append("")
        lines.append(f"### **Composite Thesis Health: {weighted_sum:.1f}%**")
        lines.append("")

        if kill_triggered:
            lines.append("### 💀 KILL SWITCH TRIGGERED — EXIT RECOMMENDED")
            lines.append("A critical pillar has broken. Thesis is invalidated regardless of composite score.")
        elif weighted_sum >= 75:
            lines.append("### ✅ Thesis Healthy — Hold/Add position")
        elif weighted_sum >= 50:
            lines.append("### ⚠️ Thesis Under Pressure — Reduce size, tighten stops")
        else:
            lines.append("### ❌ Thesis Damaged — Consider full exit")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Pillar Score Error: {str(e)}")


def _obs(content: str) -> str:
    """Wrap content in tool_observation tags."""
    return f"<tool_observation>\n{content}\n</tool_observation>"


# ────────────── ADDITIONAL COMPUTATION TOOLS ──────────────

def dupont_decomposition(params: Dict[str, Any]) -> str:
    """
    DuPont 3-factor decomposition of ROE.
    Inputs: net_income, revenue, total_assets, total_equity (all in same currency unit)
    """
    try:
        ni = float(params.get("net_income", 0))
        rev = float(params.get("revenue", 0))
        assets = float(params.get("total_assets", 0))
        equity = float(params.get("total_equity", 0))

        if rev == 0 or assets == 0 or equity == 0:
            return _obs("DuPont ERROR: revenue, total_assets, total_equity must all be > 0")

        net_margin = ni / rev
        asset_turnover = rev / assets
        equity_multiplier = assets / equity
        roe = net_margin * asset_turnover * equity_multiplier

        lines = []
        lines.append("## DuPont ROE Decomposition (Computed)")
        lines.append("")
        lines.append("| Component | Formula | Value |")
        lines.append("|-----------|---------|-------|")
        lines.append(f"| Net Profit Margin | NI / Revenue | {net_margin:.2%} |")
        lines.append(f"| Asset Turnover | Revenue / Assets | {asset_turnover:.3f}x |")
        lines.append(f"| Equity Multiplier | Assets / Equity | {equity_multiplier:.2f}x |")
        lines.append(f"| **ROE** | **Margin × Turnover × Leverage** | **{roe:.2%}** |")
        lines.append("")
        lines.append("### Interpretation")
        if net_margin > 0.15:
            lines.append(f"- High profitability ({net_margin:.1%}) — pricing power or cost leadership")
        elif net_margin < 0.05:
            lines.append(f"- Low profitability ({net_margin:.1%}) — thin margins, cost pressure")
        if asset_turnover > 1.0:
            lines.append(f"- Efficient asset use ({asset_turnover:.2f}x) — asset-light model")
        elif asset_turnover < 0.3:
            lines.append(f"- Low asset efficiency ({asset_turnover:.2f}x) — capital-intensive")
        if equity_multiplier > 3.0:
            lines.append(f"- High leverage ({equity_multiplier:.1f}x) — financial risk elevated")
        elif equity_multiplier < 1.5:
            lines.append(f"- Conservative leverage ({equity_multiplier:.1f}x) — strong balance sheet")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"DuPont Error: {str(e)}")


def minervini_stage_classifier(params: Dict[str, Any]) -> str:
    """
    Minervini Stage Analysis — classify stock's trend stage (1-4).
    Inputs: price, ma50, ma150, ma200, ma200_prev (for slope), high_52w, low_52w
    """
    try:
        price = float(params.get("price", 0))
        ma50 = float(params.get("ma50", 0))
        ma150 = float(params.get("ma150", 0))
        ma200 = float(params.get("ma200", 0))
        ma200_prev = float(params.get("ma200_prev", ma200))
        high_52w = float(params.get("high_52w", price))
        low_52w = float(params.get("low_52w", price))

        if price <= 0:
            return _obs("Minervini ERROR: price must be > 0")

        # Stage 2 criteria (Mark Minervini's Trend Template)
        criteria = {
            "price > MA150": price > ma150,
            "price > MA200": price > ma200,
            "MA150 > MA200": ma150 > ma200,
            "MA200 trending up": ma200 > ma200_prev,
            "MA50 > MA150": ma50 > ma150,
            "MA50 > MA200": ma50 > ma200,
            "price > MA50": price > ma50,
            "price ≥ 30% above 52w low": price >= low_52w * 1.30,
            "price within 25% of 52w high": price >= high_52w * 0.75,
        }

        passed = sum(1 for v in criteria.values() if v)
        total = len(criteria)

        # Determine stage
        if passed >= 8:
            stage = 2
            stage_name = "Stage 2 — ADVANCING (Uptrend)"
            action = "✅ BUY ZONE — Ideal for entries on pullbacks to rising MA50"
        elif price > ma200 and ma200 > ma200_prev and ma50 < ma150:
            stage = 1
            stage_name = "Stage 1 — BASING (Accumulation)"
            action = "⏳ WATCH — Wait for MA50 to cross above MA150 for Stage 2 entry"
        elif price < ma200 and ma200 < ma200_prev and ma50 < ma150:
            stage = 4
            stage_name = "Stage 4 — DECLINING (Downtrend)"
            action = "🚫 AVOID — Do not buy. Short candidates only."
        else:
            stage = 3
            stage_name = "Stage 3 — TOPPING (Distribution)"
            action = "⚠️ CAUTION — Reduce exposure, tighten stops"

        # VCP pattern check (if stage 2)
        pct_from_high = ((high_52w - price) / high_52w) * 100

        lines = []
        lines.append("## Minervini Stage Analysis (Computed)")
        lines.append("")
        lines.append(f"### **{stage_name}**")
        lines.append(f"### Action: {action}")
        lines.append("")
        lines.append("### Trend Template Checklist")
        lines.append("| Criterion | Result |")
        lines.append("|-----------|--------|")
        for criterion, passed_flag in criteria.items():
            icon = "✅" if passed_flag else "❌"
            lines.append(f"| {criterion} | {icon} |")
        lines.append(f"| **Score** | **{passed}/{total}** |")
        lines.append("")
        lines.append("### Key Levels")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Current Price | {price:.2f} |")
        lines.append(f"| MA50 | {ma50:.2f} |")
        lines.append(f"| MA150 | {ma150:.2f} |")
        lines.append(f"| MA200 | {ma200:.2f} |")
        lines.append(f"| 52W High | {high_52w:.2f} ({pct_from_high:.1f}% below) |")
        lines.append(f"| 52W Low | {low_52w:.2f} ({((price/low_52w)-1)*100:.1f}% above) |")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Minervini Stage Error: {str(e)}")


def earnings_quality_audit(params: Dict[str, Any]) -> str:
    """
    Earnings Quality Audit — checks OCF/NI, AR/Revenue, non-recurring items.
    Inputs: operating_cashflow, net_income, accounts_receivable, revenue, 
            non_recurring_items, prev_ar (for trend), prev_revenue (for trend)
    """
    try:
        ocf = float(params.get("operating_cashflow", 0))
        ni = float(params.get("net_income", 0))
        ar = float(params.get("accounts_receivable", 0))
        rev = float(params.get("revenue", 0))
        non_recur = float(params.get("non_recurring_items", 0))
        prev_ar = params.get("prev_ar")
        prev_rev = params.get("prev_revenue")

        if ni == 0 or rev == 0:
            return _obs("Earnings Quality ERROR: net_income and revenue must be non-zero")

        ocf_ni_ratio = ocf / ni if ni != 0 else 0
        ar_rev_ratio = (ar / rev) * 100 if rev != 0 else 0
        non_recur_pct = (abs(non_recur) / abs(ni)) * 100 if ni != 0 else 0

        # AR trend
        ar_trend = ""
        if prev_ar is not None and prev_rev is not None:
            prev_ar_rev = (float(prev_ar) / float(prev_rev)) * 100 if float(prev_rev) != 0 else 0
            ar_change = ar_rev_ratio - prev_ar_rev
            ar_trend = f" (Δ {ar_change:+.1f}pp vs prior period)"

        alerts = []
        score = 100

        # Check 1: OCF vs NI
        if ocf_ni_ratio < 0.7:
            alerts.append("🚨 OCF/NI < 70% — Earnings quality POOR. Cash generation significantly lags reported profits.")
            score -= 30
        elif ocf_ni_ratio < 1.0:
            alerts.append("⚠️ OCF/NI < 100% — Moderate concern. Cash flow slightly trails net income.")
            score -= 10

        # Check 2: AR/Revenue
        if ar_rev_ratio > 30:
            alerts.append(f"🚨 AR/Revenue = {ar_rev_ratio:.1f}% — Very high. Possible channel stuffing or collection risk.")
            score -= 25
        elif ar_rev_ratio > 20:
            alerts.append(f"⚠️ AR/Revenue = {ar_rev_ratio:.1f}% — Elevated. Monitor collection days.")
            score -= 10

        # Check 3: Non-recurring items
        if non_recur_pct > 30:
            alerts.append(f"🚨 Non-recurring = {non_recur_pct:.1f}% of NI — Earnings heavily reliant on one-offs. Strip from valuation.")
            score -= 30
        elif non_recur_pct > 20:
            alerts.append(f"⚠️ Non-recurring = {non_recur_pct:.1f}% of NI — Significant one-offs. Adjust PE accordingly.")
            score -= 15

        lines = []
        lines.append("## Earnings Quality Audit (Computed)")
        lines.append("")
        lines.append("| Metric | Value | Threshold | Status |")
        lines.append("|--------|-------|-----------|--------|")
        lines.append(f"| OCF / Net Income | {ocf_ni_ratio:.2f}x | ≥ 1.0x | {'✅' if ocf_ni_ratio >= 1.0 else '⚠️' if ocf_ni_ratio >= 0.7 else '🚨'} |")
        lines.append(f"| AR / Revenue | {ar_rev_ratio:.1f}%{ar_trend} | < 20% | {'✅' if ar_rev_ratio < 20 else '⚠️' if ar_rev_ratio < 30 else '🚨'} |")
        lines.append(f"| Non-Recurring / NI | {non_recur_pct:.1f}% | < 20% | {'✅' if non_recur_pct < 20 else '⚠️' if non_recur_pct < 30 else '🚨'} |")
        lines.append("")
        lines.append(f"### **Quality Score: {score}/100**")
        lines.append("")
        if alerts:
            lines.append("### Alerts")
            for a in alerts:
                lines.append(f"- {a}")
        else:
            lines.append("### ✅ No quality concerns detected. Earnings appear well-supported by cash flows.")
        lines.append("")
        lines.append("### Valuation Adjustment")
        if score >= 80:
            lines.append("- No adjustment needed. Use reported earnings for PE calculation.")
        elif score >= 60:
            lines.append("- Apply 5-10% discount to reported earnings in valuation models.")
        else:
            lines.append("- Apply 15-25% discount to reported earnings. Consider using OCF-based valuation instead.")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Earnings Quality Error: {str(e)}")


def drawdown_scenario(params: Dict[str, Any]) -> str:
    """
    Drawdown scenario matrix — calculate portfolio impact at various decline levels.
    Inputs: positions (list of {symbol, weight_pct, beta}), scenarios (list of market decline %)
    """
    try:
        positions = params.get("positions", [])
        scenarios = params.get("scenarios", [-10, -20, -30, -50])
        account_size = float(params.get("account_size", 100000))

        if not positions:
            return _obs("Drawdown ERROR: 'positions' list is required")

        lines = []
        lines.append("## Drawdown Scenario Matrix (Computed)")
        lines.append("")
        
        # Header
        header = "| Position | Weight | Beta |"
        for s in scenarios:
            header += f" Mkt {s}% |"
        lines.append(header)
        
        sep = "|----------|--------|------|"
        for s in scenarios:
            sep += "---------|"
        lines.append(sep)

        total_loss_by_scenario = {s: 0.0 for s in scenarios}

        for pos in positions:
            symbol = pos.get("symbol", "?")
            weight = float(pos.get("weight_pct", 0))
            beta = float(pos.get("beta", 1.0))
            
            row = f"| {symbol} | {weight:.1f}% | {beta:.2f} |"
            for s in scenarios:
                stock_decline = s * beta
                dollar_loss = account_size * (weight / 100) * (stock_decline / 100)
                total_loss_by_scenario[s] += dollar_loss
                row += f" {stock_decline:.1f}% (${abs(dollar_loss):,.0f}) |"
            lines.append(row)

        # Total row
        total_row = "| **TOTAL** | 100% | — |"
        for s in scenarios:
            total_loss = total_loss_by_scenario[s]
            total_pct = (total_loss / account_size) * 100
            total_row += f" **{total_pct:.1f}%** (${abs(total_loss):,.0f}) |"
        lines.append(total_row)
        lines.append("")
        lines.append(f"Account Size: ${account_size:,.0f}")
        lines.append("")

        # Survival check
        worst = total_loss_by_scenario[min(scenarios)]
        worst_pct = abs(worst / account_size * 100)
        if worst_pct > 50:
            lines.append(f"### 🚨 CRITICAL: {worst_pct:.0f}% max drawdown exceeds 50% — portfolio destruction risk")
        elif worst_pct > 25:
            lines.append(f"### ⚠️ WARNING: {worst_pct:.0f}% max drawdown — requires {worst_pct/(100-worst_pct)*100:.0f}% recovery gain")
        else:
            lines.append(f"### ✅ Max drawdown {worst_pct:.0f}% — manageable with proper risk controls")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Drawdown Scenario Error: {str(e)}")


def risk_reward_calculator(params: Dict[str, Any]) -> str:
    """
    Risk/Reward calculator with probability-weighted expected value.
    Inputs: entry, target, stop, win_probability (optional)
    """
    try:
        entry = float(params.get("entry", 0))
        target = float(params.get("target", 0))
        stop = float(params.get("stop", 0))
        win_prob = params.get("win_probability")

        if entry <= 0:
            return _obs("Risk/Reward ERROR: entry must be > 0")

        reward = abs(target - entry)
        risk = abs(entry - stop)
        
        if risk == 0:
            return _obs("Risk/Reward ERROR: stop cannot equal entry")

        rr_ratio = reward / risk
        reward_pct = (reward / entry) * 100
        risk_pct = (risk / entry) * 100

        lines = []
        lines.append("## Risk/Reward Analysis (Computed)")
        lines.append("")
        lines.append("| Parameter | Value |")
        lines.append("|-----------|-------|")
        lines.append(f"| Entry | {entry:.2f} |")
        lines.append(f"| Target | {target:.2f} ({reward_pct:+.1f}%) |")
        lines.append(f"| Stop Loss | {stop:.2f} ({-risk_pct:.1f}%) |")
        lines.append(f"| Reward | {reward:.2f} |")
        lines.append(f"| Risk | {risk:.2f} |")
        lines.append(f"| **R:R Ratio** | **{rr_ratio:.2f}:1** |")

        if win_prob is not None:
            p = float(win_prob)
            ev = p * reward - (1 - p) * risk
            ev_pct = (ev / entry) * 100
            breakeven_wr = 1 / (1 + rr_ratio)
            lines.append(f"| Win Probability | {p:.0%} |")
            lines.append(f"| Expected Value | {ev:.2f} ({ev_pct:+.2f}%) |")
            lines.append(f"| Breakeven Win Rate | {breakeven_wr:.0%} |")
            lines.append("")
            if ev > 0:
                lines.append(f"### ✅ Positive Expected Value (+{ev:.2f})")
                lines.append(f"With {p:.0%} win rate and {rr_ratio:.1f}:1 R:R, this trade has edge.")
            else:
                lines.append(f"### ❌ Negative Expected Value ({ev:.2f})")
                lines.append(f"Need >{breakeven_wr:.0%} win rate to break even at this R:R.")
        else:
            breakeven_wr = 1 / (1 + rr_ratio)
            lines.append("")
            lines.append(f"### Breakeven Win Rate: {breakeven_wr:.0%}")
            if rr_ratio >= 3:
                lines.append("### ✅ Excellent R:R — Asymmetric setup")
            elif rr_ratio >= 2:
                lines.append("### ✅ Good R:R — Favorable")
            elif rr_ratio >= 1:
                lines.append("### ⚠️ Fair R:R — Acceptable only with high conviction")
            else:
                lines.append("### ❌ Poor R:R — Risk exceeds reward. Reconsider.")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Risk/Reward Error: {str(e)}")


def stop_loss_validator(params: Dict[str, Any]) -> str:
    """
    Validate stop-loss feasibility against volatility.
    Inputs: entry_price, stop_price, atr (Average True Range), daily_volatility_pct
    """
    try:
        entry = float(params.get("entry_price", 0))
        stop = float(params.get("stop_price", 0))
        atr = float(params.get("atr", 0))
        daily_vol = params.get("daily_volatility_pct")

        if entry <= 0 or stop <= 0:
            return _obs("Stop Validation ERROR: prices must be > 0")

        stop_distance = abs(entry - stop)
        stop_pct = (stop_distance / entry) * 100

        lines = []
        lines.append("## Stop-Loss Feasibility Check (Computed)")
        lines.append("")
        lines.append("| Parameter | Value |")
        lines.append("|-----------|-------|")
        lines.append(f"| Entry Price | {entry:.2f} |")
        lines.append(f"| Stop Price | {stop:.2f} |")
        lines.append(f"| Stop Distance | {stop_distance:.2f} ({stop_pct:.2f}%) |")

        warnings = []

        if atr > 0:
            atr_multiples = stop_distance / atr
            lines.append(f"| ATR (14-day) | {atr:.2f} |")
            lines.append(f"| Stop = ATR × | {atr_multiples:.2f}x |")
            
            if atr_multiples < 1.0:
                warnings.append(f"🚨 Stop is INSIDE 1 ATR ({atr_multiples:.1f}x) — will be hit by normal noise. Widen to ≥1.5 ATR.")
            elif atr_multiples < 1.5:
                warnings.append(f"⚠️ Stop is tight ({atr_multiples:.1f}x ATR) — moderate whipsaw risk.")
            elif atr_multiples > 3.0:
                warnings.append(f"⚠️ Stop is very wide ({atr_multiples:.1f}x ATR) — large loss if triggered. Consider smaller position.")

        if daily_vol is not None:
            dv = float(daily_vol)
            days_to_hit = stop_pct / dv if dv > 0 else 999
            lines.append(f"| Daily Volatility | {dv:.2f}% |")
            lines.append(f"| Days of vol to hit stop | {days_to_hit:.1f} |")
            
            if days_to_hit < 1:
                warnings.append(f"🚨 Stop can be hit in < 1 day of normal movement — extremely tight")
            elif days_to_hit < 3:
                warnings.append(f"⚠️ Stop within 3 days of normal vol — may be stopped out by noise")

        lines.append("")
        if warnings:
            lines.append("### Warnings")
            for w in warnings:
                lines.append(f"- {w}")
        else:
            lines.append("### ✅ Stop placement is reasonable relative to volatility")

        lines.append("")
        lines.append("### Recommended Stop Levels")
        if atr > 0:
            lines.append(f"| Method | Stop Price |")
            lines.append(f"|--------|-----------|")
            lines.append(f"| 1.5× ATR | {entry - 1.5 * atr:.2f} |")
            lines.append(f"| 2.0× ATR | {entry - 2.0 * atr:.2f} |")
            lines.append(f"| 2.5× ATR | {entry - 2.5 * atr:.2f} |")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"Stop Validation Error: {str(e)}")


def cagr_calculator(params: Dict[str, Any]) -> str:
    """
    CAGR and growth metrics calculator.
    Inputs: start_value, end_value, years. Optional: intermediate_values (for consistency check)
    """
    try:
        start = float(params.get("start_value", 0))
        end = float(params.get("end_value", 0))
        years = float(params.get("years", 1))
        intermediate = params.get("intermediate_values", [])

        if start <= 0 or end <= 0 or years <= 0:
            return _obs("CAGR ERROR: start_value, end_value, years must all be > 0")

        cagr = (end / start) ** (1 / years) - 1
        total_growth = (end / start - 1) * 100

        lines = []
        lines.append("## Growth Analysis (Computed)")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Start Value | {start:,.2f} |")
        lines.append(f"| End Value | {end:,.2f} |")
        lines.append(f"| Period | {years:.1f} years |")
        lines.append(f"| Total Growth | {total_growth:+.1f}% |")
        lines.append(f"| **CAGR** | **{cagr:.2%}** |")

        # Rule of 72
        if cagr > 0:
            doubling_time = 72 / (cagr * 100)
            lines.append(f"| Doubling Time | {doubling_time:.1f} years |")

        # Consistency check with intermediates
        if intermediate:
            lines.append("")
            lines.append("### Year-by-Year Growth")
            lines.append("| Year | Value | YoY Growth | vs CAGR |")
            lines.append("|------|-------|-----------|---------|")
            all_values = [start] + [float(v) for v in intermediate] + [end]
            for i in range(1, len(all_values)):
                yoy = (all_values[i] / all_values[i-1] - 1) * 100
                vs_cagr = yoy - cagr * 100
                lines.append(f"| Y{i} | {all_values[i]:,.2f} | {yoy:+.1f}% | {vs_cagr:+.1f}pp |")

        return _obs("\n".join(lines))
    except Exception as e:
        return _obs(f"CAGR Error: {str(e)}")


# ────────────── TOOL REGISTRY ──────────────

COMPUTATION_TOOLS = {
    "dcf_calculator": dcf_calculate,
    "position_sizer": position_size_calculate,
    "kelly_calculator": kelly_calculate,
    "beat_miss_scorer": beat_miss_score,
    "comps_valuation": comps_valuation,
    "pillar_scorer": pillar_score,
    "dupont_decomposition": dupont_decomposition,
    "minervini_stage": minervini_stage_classifier,
    "earnings_quality_audit": earnings_quality_audit,
    "drawdown_scenario": drawdown_scenario,
    "risk_reward": risk_reward_calculator,
    "stop_loss_validator": stop_loss_validator,
    "cagr_calculator": cagr_calculator,
}


def execute_computation_tool(tool_name: str, params: Dict[str, Any]) -> Optional[str]:
    """Execute a computation tool by name. Returns None if tool not found."""
    fn = COMPUTATION_TOOLS.get(tool_name)
    if fn:
        return fn(params)
    return None
