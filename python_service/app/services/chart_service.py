import io
import base64
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
import logging

logger = logging.getLogger(__name__)

# Use Agg backend for headless plotting
plt.switch_backend('Agg')

class ChartService:
    @staticmethod
    def _df_to_base64(fig) -> str:
        """Helper to convert a matplotlib figure to base64 string."""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        return img_str

    @staticmethod
    def generate_candlestick_chart(df: pd.DataFrame, title: str = "Price Chart") -> str:
        """
        Generate a candlestick chart with volume.
        Expected DataFrame columns: Open, High, Low, Close, Volume
        Index should be DatetimeIndex.
        Returns Base64 encoded PNG.
        """
        if df.empty:
            logger.warning("Empty dataframe provided to generate_candlestick_chart")
            return ""

        try:
            # Ensure index is datetime
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            # Map columns to mplfinance expected if needed, assuming standard capitalization
            cols = {c.lower(): c for c in df.columns}
            required = ['open', 'high', 'low', 'close', 'volume']
            
            # Simple check if required columns exist (case-insensitive)
            plot_df = pd.DataFrame()
            for req in required:
                if req in cols:
                    plot_df[req.capitalize()] = df[cols[req]]
                else:
                    logger.warning(f"Missing column '{req}' for candlestick chart")
                    return ""

            fig, axlist = mpf.plot(
                plot_df,
                type='candle',
                volume=True,
                title=title,
                style='yahoo',
                returnfig=True,
                figsize=(10, 6)
            )
            return ChartService._df_to_base64(fig)
        except Exception as e:
            logger.error(f"Error generating candlestick chart: {e}", exc_info=True)
            return ""

    @staticmethod
    def generate_return_distribution_chart(returns: pd.Series, title: str = "Return Distribution") -> str:
        """
        Generate a histogram of returns.
        Returns Base64 encoded PNG.
        """
        if returns.empty:
            logger.warning("Empty series provided to generate_return_distribution_chart")
            return ""

        try:
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.hist(returns.dropna(), bins=50, color='skyblue', edgecolor='black', alpha=0.7)
            ax.set_title(title)
            ax.set_xlabel('Returns')
            ax.set_ylabel('Frequency')
            ax.grid(True, alpha=0.3)
            return ChartService._df_to_base64(fig)
        except Exception as e:
            logger.error(f"Error generating return distribution chart: {e}", exc_info=True)
            return ""

chart_service = ChartService()
