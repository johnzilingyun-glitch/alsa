from typing import Optional, List, Dict
from sqlmodel import Session
from ..db.repositories.mock_trading_repo import MockTradingRepo
from ..db.models import MockTrade, MockAccount, MARKET_DEFAULT_BALANCE
import logging
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
try:
    from paper_trading_system.execution_layer.market_configs import get_exchange_kwargs
except ImportError:
    def get_exchange_kwargs(market): return {"trade_unit": 1}

logger = logging.getLogger(__name__)

# Anomaly thresholds (user-confirmed)
STOCK_ANOMALY_THRESHOLD_PCT = 7.0   # single stock daily move > ±7%
ACCOUNT_ANOMALY_THRESHOLD_PCT = 3.0 # total account equity daily move > ±3%


class MockTradingService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = MockTradingRepo(session)

    def _get_exchange_rate(self, from_curr: str, to_curr: str) -> float:
        """Static FX rates for mock trading."""
        if from_curr == to_curr:
            return 1.0
        
        rates_to_usd = {
            "USD": 1.0,
            "CNY": 0.138,  # 1 CNY ~ 0.138 USD
            "HKD": 0.128,  # 1 HKD ~ 0.128 USD
        }
        
        from_usd = rates_to_usd.get(from_curr, 1.0)
        to_usd = rates_to_usd.get(to_curr, 1.0)
        
        # from -> USD -> to
        return from_usd / to_usd

    # ── Account Management ────────────────────────────────────────

    def create_account(
        self,
        name: str,
        market: str = "A-Share",
        user_id: str = "default_user",
        initial_balance: Optional[float] = None,
    ) -> MockAccount:
        return self.repo.create_account(name=name, market=market, user_id=user_id, initial_balance=initial_balance)

    def delete_account(self, account_id: str) -> bool:
        return self.repo.delete_account(account_id)

    def list_accounts(self, user_id: str = "default_user") -> List[MockAccount]:
        return self.repo.list_accounts(user_id)

    def merge_accounts(self, source_account_ids: List[str], target_account_id: str) -> Optional[MockAccount]:
        """Merge multiple source accounts into one target account, applying FX to cash."""
        target_account = self.repo.get_account(target_account_id)
        if not target_account:
            logger.error(f"Target account {target_account_id} not found.")
            return None

        total_cash_to_add = 0.0
        total_initial_balance_to_add = 0.0

        for source_id in source_account_ids:
            src_acc = self.repo.get_account(source_id)
            if src_acc and src_acc.status == "active" and src_acc.account_id != target_account_id:
                fx = self._get_exchange_rate(src_acc.currency, target_account.currency)
                total_cash_to_add += src_acc.current_cash * fx
                total_initial_balance_to_add += src_acc.initial_balance * fx
        
        if total_cash_to_add > 0 or len(source_account_ids) > 0:
            return self.repo.merge_accounts(
                source_account_ids=source_account_ids,
                target_account_id=target_account_id,
                total_cash_to_add=total_cash_to_add,
                total_initial_balance_to_add=total_initial_balance_to_add,
            )
        return target_account

    # ── Trade Execution ───────────────────────────────────────────

    def execute_trade(
        self,
        account_id: str,
        symbol: str,
        market: str,
        action: str,
        shares: int,
        execution_price: float,
        trigger_source: str,
        related_alert_id: Optional[str] = None,
        position_size_pct: Optional[float] = None,
    ) -> Optional[MockTrade]:
        """Execute a mock trade. Updates cash, position, and records the trade."""
        account = self.repo.get_account(account_id)
        if not account or account.status != "active":
            logger.error(f"Cannot execute trade. Account {account_id} not found or inactive.")
            return None

        market_cfg = get_exchange_kwargs(market)
        open_cost_rate = market_cfg.get("open_cost", 0.0)
        close_cost_rate = market_cfg.get("close_cost", 0.0)
        min_cost = market_cfg.get("min_cost", 0.0)

        from ..db.models import MARKET_CURRENCY
        trade_currency = MARKET_CURRENCY.get(market, "CNY")
        fx_rate = self._get_exchange_rate(trade_currency, account.currency)

        trade_value = shares * execution_price
        realized_pnl = None

        if action == "BUY":
            cost = max(trade_value * open_cost_rate, min_cost)
            total_required = trade_value + cost
            total_required_base = total_required * fx_rate
            
            if account.current_cash < total_required_base:
                logger.error(f"Insufficient funds in {account_id}. Need {total_required_base} {account.currency}, have {account.current_cash}.")
                return None

            self.repo.update_cash(account_id, -total_required_base)

            pos = self.repo.get_position(account_id, symbol, market)
            if pos and pos.shares > 0:
                new_shares = pos.shares + shares
                new_cost = ((pos.shares * pos.average_cost) + total_required) / new_shares
                self.repo.upsert_position(account_id, symbol, market, new_shares, new_cost)
            else:
                self.repo.upsert_position(account_id, symbol, market, shares, total_required / shares if shares > 0 else 0)

        elif action == "SELL":
            pos = self.repo.get_position(account_id, symbol, market)
            if not pos or pos.shares < shares:
                logger.error(f"Insufficient shares in {account_id} to sell {shares} of {symbol}.")
                return None

            cost = max(trade_value * close_cost_rate, min_cost)
            total_received = trade_value - cost
            total_received_base = total_received * fx_rate
            
            # Calculate realized PnL against average cost (in trade currency, then converted to base)
            realized_pnl = (total_received - (pos.average_cost * shares)) * fx_rate

            self.repo.update_cash(account_id, total_received_base)

            new_shares = pos.shares - shares
            if new_shares == 0:
                self.repo.upsert_position(account_id, symbol, market, 0, 0.0)
            else:
                self.repo.upsert_position(account_id, symbol, market, new_shares, pos.average_cost)
        else:
            logger.error(f"Unknown action {action}")
            return None

        trade = self.repo.record_trade(
            account_id=account_id,
            symbol=symbol,
            market=market,
            action=action,
            shares=shares,
            execution_price=execution_price,
            trigger_source=trigger_source,
            related_alert_id=related_alert_id,
            position_size_pct=position_size_pct,
            realized_pnl=realized_pnl,
        )
        return trade

    # ── Signal-Triggered Auto-Trade ──────────────────────────────

    def check_and_execute_signal(
        self,
        account_id: str,
        alert: Dict,
        current_price: float,
    ) -> Optional[MockTrade]:
        """
        Check if current_price triggers a signal entry/exit and execute accordingly.
        `alert` is a dict with keys: alert_id, symbol, market, entry_price, target_price, stop_loss,
                                      position_size_pct (from AI).
        """
        symbol = alert["symbol"]
        market = alert["market"]
        alert_id = alert.get("alert_id")
        ai_size_pct = alert.get("position_size_pct", 10.0)  # default 10% if AI didn't specify

        account = self.repo.get_account(account_id)
        if not account or account.status != "active":
            return None

        pos = self.repo.get_position(account_id, symbol, market)
        has_position = pos and pos.shares > 0

        # ── SELL triggers (only if we hold the stock) ──
        if has_position:
            if current_price >= alert["target_price"]:
                logger.info(f"[SIGNAL] Target hit for {symbol} @ {current_price}. Selling all.")
                return self.execute_trade(
                    account_id, symbol, market, "SELL", pos.shares,
                    current_price, "AI_SIGNAL", alert_id, ai_size_pct,
                )
            if current_price <= alert["stop_loss"]:
                logger.info(f"[SIGNAL] Stop-loss hit for {symbol} @ {current_price}. Selling all.")
                return self.execute_trade(
                    account_id, symbol, market, "SELL", pos.shares,
                    current_price, "AI_SIGNAL", alert_id, ai_size_pct,
                )

        # ── BUY trigger (only if we don't already hold) ──
        if not has_position and current_price <= alert["entry_price"]:
            # Calculate shares from AI-specified position size %
            equity = self._estimate_equity(account, {})
            budget = equity * (ai_size_pct / 100.0)
            raw_shares = budget / current_price
            
            # Apply market-specific trade unit rounding (e.g. 100 for A-Share)
            market_cfg = get_exchange_kwargs(market)
            trade_unit = market_cfg.get("trade_unit", 1)
            shares = int(raw_shares // trade_unit) * trade_unit
            
            if shares <= 0:
                logger.warning(f"[SIGNAL] Budget too small to buy 1 unit of {symbol}. Budget: {budget}, Price: {current_price}, Unit: {trade_unit}")
                return None
            logger.info(f"[SIGNAL] Entry hit for {symbol} @ {current_price}. Buying {shares} shares ({ai_size_pct}% of equity).")
            return self.execute_trade(
                account_id, symbol, market, "BUY", shares,
                current_price, "AI_SIGNAL", alert_id, ai_size_pct,
            )

        return None

    # ── Portfolio Analytics ───────────────────────────────────────

    def get_portfolio_summary(self, account_id: str, price_map: Dict[str, float]) -> Optional[Dict]:
        """
        Return a portfolio summary with current equity, PnL, and per-position detail.
        price_map: { "AAPL": 190.5, "601398.SH": 5.12 }
        """
        account = self.repo.get_account(account_id)
        if not account:
            return None

        positions = self.repo.list_positions(account_id)
        pos_details = []
        total_market_value = 0.0

        from ..db.models import MARKET_CURRENCY
        
        for p in positions:
            trade_currency = MARKET_CURRENCY.get(p.market, "CNY")
            fx_rate = self._get_exchange_rate(trade_currency, account.currency)
            
            cur_price = price_map.get(p.symbol, p.average_cost)
            mkt_val_trade = cur_price * p.shares
            unrealized_trade = (cur_price - p.average_cost) * p.shares
            unrealized_pct = ((cur_price / p.average_cost) - 1) * 100 if p.average_cost > 0 else 0
            
            mkt_val_base = mkt_val_trade * fx_rate
            unrealized_base = unrealized_trade * fx_rate
            
            total_market_value += mkt_val_base
            pos_details.append({
                "symbol": p.symbol,
                "market": p.market,
                "shares": p.shares,
                "average_cost": p.average_cost,
                "current_price": cur_price,
                "market_value": round(mkt_val_base, 2),
                "unrealized_pnl": round(unrealized_base, 2),
                "unrealized_pnl_pct": round(unrealized_pct, 2),
            })

        total_equity = account.current_cash + total_market_value
        total_pnl = total_equity - account.initial_balance
        total_pnl_pct = ((total_equity / account.initial_balance) - 1) * 100 if account.initial_balance > 0 else 0

        return {
            "account_id": account.account_id,
            "name": account.name,
            "market": account.market,
            "currency": account.currency,
            "initial_balance": account.initial_balance,
            "current_cash": round(account.current_cash, 2),
            "positions_market_value": round(total_market_value, 2),
            "total_equity": round(total_equity, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "positions": pos_details,
        }

    def _estimate_equity(self, account: MockAccount, price_map: Dict[str, float]) -> float:
        """Quick equity estimate. Falls back to cash if no prices available."""
        from ..db.models import MARKET_CURRENCY
        
        positions = self.repo.list_positions(account.account_id)
        mkt_val = 0.0
        for p in positions:
            trade_currency = MARKET_CURRENCY.get(p.market, "CNY")
            fx_rate = self._get_exchange_rate(trade_currency, account.currency)
            mkt_val += price_map.get(p.symbol, p.average_cost) * p.shares * fx_rate
            
        return account.current_cash + mkt_val

    # ── Anomaly Detection ─────────────────────────────────────────

    def check_anomalies(
        self,
        account_id: str,
        price_changes: Dict[str, float],  # { "AAPL": -8.5, "TSLA": 12.3 } in %
        account_equity_change_pct: Optional[float] = None,
    ) -> List[Dict]:
        """
        Check for anomalies in position stock moves and account equity swings.
        Returns list of dicts with anomaly info for each trigger.
        """
        anomalies = []

        # Per-stock check
        for symbol, change_pct in price_changes.items():
            if abs(change_pct) >= STOCK_ANOMALY_THRESHOLD_PCT:
                event_type = "SPIKE" if change_pct > 0 else "DROP"
                entry = self.repo.log_anomaly(
                    account_id=account_id,
                    event_type=event_type,
                    magnitude_pct=round(change_pct, 2),
                    symbol=symbol,
                )
                anomalies.append({
                    "log_id": entry.log_id,
                    "symbol": symbol,
                    "event_type": event_type,
                    "magnitude_pct": change_pct,
                })

        # Account-level check
        if account_equity_change_pct is not None and abs(account_equity_change_pct) >= ACCOUNT_ANOMALY_THRESHOLD_PCT:
            event_type = "SPIKE" if account_equity_change_pct > 0 else "DROP"
            entry = self.repo.log_anomaly(
                account_id=account_id,
                event_type=event_type,
                magnitude_pct=round(account_equity_change_pct, 2),
            )
            anomalies.append({
                "log_id": entry.log_id,
                "symbol": None,
                "event_type": event_type,
                "magnitude_pct": account_equity_change_pct,
            })

        return anomalies
