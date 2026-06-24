import logging
import asyncio
from datetime import timedelta
import pandas as pd
from sqlmodel import select
from app.db.models import PredictionRecord
from app.db.database import session_factory
from app.services.data_providers.router import data_router
from app.time_utils import utc_now

logger = logging.getLogger(__name__)

class PredictionService:
    @staticmethod
    def get_horizon_days(horizon: str) -> int:
        if horizon == "1_month":
            return 30
        elif horizon == "3_months":
            return 90
        elif horizon == "6_months":
            return 180
        elif horizon == "1_year":
            return 365
        
        # Try parsing format like "X_days" or "X_months" or "X_years"
        try:
            parts = horizon.split("_")
            if parts[0].isdigit():
                num = int(parts[0])
                if "day" in horizon:
                    return num
                elif "month" in horizon:
                    return num * 30
                elif "year" in horizon:
                    return num * 365
        except Exception:
            pass
        return 30

    @classmethod
    async def evaluate_pending_predictions(cls):
        """
        Scan PredictionRecord table for pending predictions that have reached their horizon,
        fetch actual price, compute accuracy score, and mark as evaluated.
        """
        logger.info("Scanning for pending predictions to evaluate...")
        
        try:
            session = session_factory()
        except Exception as e:
            logger.error(f"Failed to create DB session in prediction loop: {e}")
            return
            
        try:
            # Query all pending prediction records
            statement = select(PredictionRecord).where(PredictionRecord.status == "pending")
            pending_records = session.exec(statement).all()
            
            if not pending_records:
                logger.info("No pending predictions found.")
                return
            
            now_dt = utc_now()
            updated_count = 0
            
            for pred in pending_records:
                days = cls.get_horizon_days(pred.time_horizon)
                horizon_dt = pred.created_at + timedelta(days=days)
                
                # Check if we've reached the time horizon
                if now_dt < horizon_dt:
                    continue
                
                logger.info(f"Evaluating prediction {pred.prediction_id} for {pred.symbol} (horizon reached at {horizon_dt})")
                
                # Fetch history. Period should be large enough to contain the horizon date.
                # Request "1y" or "2y" period based on time horizon.
                period = "1y"
                if days > 180:
                    period = "2y"
                
                try:
                    df = await data_router.get_history(pred.symbol, period=period)
                    if df is None or df.empty:
                        logger.warning(f"No history found for {pred.symbol} to evaluate prediction {pred.prediction_id}")
                        continue
                    
                    # Look up closest date to horizon_dt
                    df['date_dt'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                    horizon_naive = horizon_dt.replace(tzinfo=None)
                    df['time_diff'] = (df['date_dt'] - horizon_naive).abs()
                    
                    closest_idx = df['time_diff'].idxmin()
                    closest_row = df.loc[closest_idx]
                    
                    # Accept if closest date is within a reasonable window (e.g. 5 days to account for weekends/holidays)
                    if closest_row['time_diff'] <= pd.Timedelta(days=5):
                        actual_price = float(closest_row['close'])
                        
                        # Evaluate prediction using standard evaluation logic
                        initial = pred.current_price_at_prediction
                        target = pred.target_price
                        
                        expected_direction = 1 if target > initial else -1 if target < initial else 0
                        actual_direction = 1 if actual_price > initial else -1 if actual_price < initial else 0
                        
                        if expected_direction == 0:
                            deviation = abs(actual_price - initial) / initial
                            score = max(0, 100 - deviation * 1000)
                        else:
                            expected_move = abs(target - initial) / initial
                            actual_move = (actual_price - initial) / initial
                            
                            if expected_direction != actual_direction:
                                score = max(0, 50 - (abs(actual_move) / expected_move) * 50 if expected_move > 0 else 0)
                            else:
                                target_diff = abs(actual_price - target) / target
                                score = max(0, 100 - (target_diff * 200))
                        
                        pred.actual_price_at_horizon = actual_price
                        pred.accuracy_score = score
                        pred.status = "evaluated"
                        session.add(pred)
                        updated_count += 1
                        logger.info(f"Prediction {pred.prediction_id} evaluated: actual_price={actual_price}, score={score:.2f}")
                    else:
                        logger.warning(
                            f"Closest price date {closest_row['date']} too far from horizon {horizon_dt} for {pred.symbol}"
                        )
                except Exception as e:
                    logger.error(f"Error evaluating prediction {pred.prediction_id}: {e}")
            
            if updated_count > 0:
                session.commit()
                logger.info(f"Successfully evaluated {updated_count} predictions.")
        finally:
            session.close()

    @classmethod
    async def run_accuracy_loop(cls, interval_seconds: int = 3600):
        """
        Background task to periodically evaluate pending predictions.
        """
        logger.info(f"Starting Prediction Accuracy Evaluation loop (interval: {interval_seconds}s)")
        while True:
            try:
                await cls.evaluate_pending_predictions()
            except Exception as e:
                logger.error(f"Prediction Accuracy loop error: {e}")
            await asyncio.sleep(interval_seconds)
