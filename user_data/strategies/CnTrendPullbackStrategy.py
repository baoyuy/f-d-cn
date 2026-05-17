# pragma pylint: disable=missing-docstring, invalid-name

from pandas import DataFrame

import talib.abstract as ta
from technical import qtpylib

from freqtrade.strategy import IStrategy


class CnTrendPullbackStrategy(IStrategy):
    """
    Conservative spot trend-pullback strategy for Binance-style USDT pairs.

    This strategy only enters long positions when the market is in an EMA50/EMA200
    uptrend and RSI recovers from a pullback zone. It must be backtested and
    validated in dry-run mode before any live trading.
    """

    INTERFACE_VERSION = 3

    can_short: bool = False
    timeframe = "5m"
    startup_candle_count: int = 200
    process_only_new_candles = True

    minimal_roi = {
        "120": 0.0,
        "60": 0.01,
        "30": 0.02,
        "0": 0.04,
    }

    stoploss = -0.08

    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC",
    }

    plot_config = {
        "main_plot": {
            "ema50": {"color": "orange"},
            "ema200": {"color": "blue"},
            "bb_lowerband": {"color": "grey"},
            "bb_middleband": {"color": "grey"},
            "bb_upperband": {"color": "grey"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "red"},
            },
            "ADX": {
                "adx": {"color": "purple"},
            },
        },
    }

    def informative_pairs(self):
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean()

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_percent"] = (
            (dataframe["close"] - dataframe["bb_lowerband"])
            / (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trend_filter = (
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["ema200"])
            & (dataframe["adx"] > 18)
        )

        pullback_filter = (
            (dataframe["close"] <= dataframe["ema50"] * 1.015)
            | (dataframe["close"] <= dataframe["bb_middleband"])
        )

        momentum_recovery = qtpylib.crossed_above(dataframe["rsi"], 35)

        volume_filter = (
            (dataframe["volume"] > 0)
            & (dataframe["volume"] > dataframe["volume_mean_20"] * 0.5)
        )

        dataframe.loc[
            (
                trend_filter
                & pullback_filter
                & momentum_recovery
                & volume_filter
                & (dataframe["bb_percent"] < 0.65)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        take_profit_signal = qtpylib.crossed_above(dataframe["rsi"], 70)
        trend_break_signal = qtpylib.crossed_below(dataframe["close"], dataframe["ema50"])
        trend_reversal_signal = qtpylib.crossed_below(dataframe["ema50"], dataframe["ema200"])

        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (take_profit_signal | trend_break_signal | trend_reversal_signal)
            ),
            "exit_long",
        ] = 1

        return dataframe
