# pragma pylint: disable=missing-docstring, invalid-name

from pandas import DataFrame

import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class CnStrongTrendStrategy(IStrategy):
    """
    Spot-only strength and trend breakout strategy.

    Designed for a dynamic USDT pair universe. It looks for liquid coins already
    trending on the 1h chart, then enters on 15m momentum breakouts with volume
    expansion. Backtest and dry-run validation are mandatory before live trading.
    """

    INTERFACE_VERSION = 3

    can_short: bool = False
    timeframe = "15m"
    startup_candle_count: int = 240
    process_only_new_candles = True

    minimal_roi = {
        "240": 0.0,
        "120": 0.02,
        "60": 0.04,
        "0": 0.08,
    }

    stoploss = -0.06

    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.05
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = True

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
            "ema20": {"color": "green"},
            "ema50": {"color": "orange"},
            "ema200": {"color": "blue"},
            "breakout_high": {"color": "white"},
        },
        "subplots": {
            "Momentum": {
                "rsi": {"color": "red"},
                "adx": {"color": "purple"},
            },
            "Volume": {
                "relative_volume": {"color": "cyan"},
            },
        },
    }

    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["trend_strength"] = (
            (dataframe["ema50"] - dataframe["ema200"]) / dataframe["ema200"]
        )

        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_mean_50"] = dataframe["volume"].rolling(50).mean()
        dataframe["relative_volume"] = dataframe["volume"] / dataframe["volume_mean_20"]

        dataframe["breakout_high"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["recent_low"] = dataframe["low"].rolling(10).min()
        dataframe["price_change_12"] = dataframe["close"].pct_change(12)
        dataframe["ema20_slope"] = dataframe["ema20"].pct_change(3)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        higher_timeframe_trend = (
            (dataframe["ema50_1h"] > dataframe["ema200_1h"])
            & (dataframe["close"] > dataframe["ema50_1h"])
            & (dataframe["trend_strength_1h"] > 0.003)
            & (dataframe["adx_1h"] > 18)
        )

        local_trend = (
            (dataframe["close"] > dataframe["ema20"])
            & (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["ema20_slope"] > 0)
        )

        momentum = (
            (dataframe["rsi"] > 52)
            & (dataframe["rsi"] < 78)
            & (dataframe["rsi"] > dataframe["rsi"].shift(1))
            & (dataframe["adx"] > 18)
        )

        breakout = (
            (dataframe["close"] > dataframe["breakout_high"])
            | (
                (dataframe["close"] > dataframe["high"].rolling(10).max().shift(1))
                & (dataframe["price_change_12"] > 0.015)
            )
        )

        volume_expansion = (
            (dataframe["volume"] > 0)
            & (dataframe["volume"] > dataframe["volume_mean_20"] * 1.2)
            & (dataframe["volume_mean_20"] > dataframe["volume_mean_50"] * 0.8)
        )

        dataframe.loc[
            higher_timeframe_trend
            & local_trend
            & momentum
            & breakout
            & volume_expansion,
            ["enter_long", "enter_tag"],
        ] = (1, "strong_trend_breakout")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trend_loss = (
            (dataframe["close"] < dataframe["ema50"])
            | (dataframe["ema20"] < dataframe["ema50"])
            | (dataframe["rsi"] < 48)
        )

        exhaustion = (
            (dataframe["rsi"] > 82)
            & (dataframe["close"] < dataframe["close"].shift(1))
            & (dataframe["volume"] > dataframe["volume_mean_20"] * 1.5)
        )

        dataframe.loc[
            (dataframe["volume"] > 0) & (trend_loss | exhaustion),
            ["exit_long", "exit_tag"],
        ] = (1, "trend_weak_or_exhausted")

        return dataframe
