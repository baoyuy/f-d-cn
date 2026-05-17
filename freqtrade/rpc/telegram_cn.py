# pragma pylint: disable=unused-argument

"""
Chinese Telegram communication layer.

This module keeps the original Telegram implementation intact and adds a Chinese
friendly wrapper around commands, keyboard labels, and outgoing messages.
"""

import asyncio
import logging
import re
from copy import deepcopy
from datetime import datetime
from functools import partial
from typing import Any, Callable

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TelegramError
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from freqtrade.enums import MarketDirection, RPCMessageType, SignalDirection, TradingMode
from freqtrade.rpc.rpc import RPCException
from freqtrade.rpc.rpc_types import RPCEntryMsg, RPCExitMsg, RPCSendMsg
from freqtrade.rpc.telegram import Telegram, authorized_only
from freqtrade.util import fmt_coin, fmt_coin2, format_pct, round_value


logger = logging.getLogger(__name__)


STATUS_WORDS = {
    "running": "运行中",
    "stopped": "已停止",
    "paused": "已暂停",
    "reloading config": "正在重载配置",
    "process died": "进程已退出",
    "stopping": "正在停止",
}


KEYBOARD_LABELS = {
    "/daily": "日报",
    "/profit": "收益",
    "/balance": "余额",
    "/status": "状态",
    "/status table": "状态表",
    "/performance": "表现",
    "/count": "持仓数",
    "/start": "启动",
    "/stop": "停止",
    "/help": "帮助",
}


TEXT_REPLACEMENTS = (
    ("<b>Performance:</b>", "<b>交易对表现:</b>"),
    ("<b>Entry Tag Performance:</b>", "<b>入场标签表现:</b>"),
    ("<b>Exit Reason Performance:</b>", "<b>出场原因表现:</b>"),
    ("<b>Mix Tag Performance:</b>", "<b>标签组合表现:</b>"),
    ("*Entry Tag Performance:*", "*入场标签表现:*"),
    ("*Exit Reason Performance:*", "*出场原因表现:*"),
    ("*Mix Tag Performance:*", "*标签组合表现:*"),
    ("*Status:*", "*状态:*"),
    ("Status:", "状态:"),
    ("*Warning:*", "*警告:*"),
    ("*ERROR:*", "*错误:*"),
    ("*Trade ID:*", "*交易 ID:*"),
    ("*Current Pair:*", "*当前交易对:*"),
    ("*Pair:*", "*交易对:*"),
    ("*Direction:*", "*方向:*"),
    ("*Amount:*", "*数量:*"),
    ("*Total invested:*", "*累计投入:*"),
    ("*Enter Tag:*", "*入场标签:*"),
    ("*Exit Reason:*", "*出场原因:*"),
    ("*Open Rate:*", "*开仓价格:*"),
    ("*Close Rate:*", "*平仓价格:*"),
    ("*Current Rate:*", "*当前价格:*"),
    ("*Exit Rate:*", "*出场价格:*"),
    ("*Open Date:*", "*开仓时间:*"),
    ("*Close Date:*", "*平仓时间:*"),
    ("*Unrealized Profit:*", "*浮动收益:*"),
    ("*Close Profit: *", "*平仓收益:* "),
    ("*Realized Profit:*", "*已实现收益:*"),
    ("*Total Profit:*", "*总收益:*"),
    ("*Initial Stoploss:*", "*初始止损:*"),
    ("*Stoploss:*", "*止损:*"),
    ("*Stoploss distance:*", "*止损距离:*"),
    ("*Stoploss rate:*", "*止损价格:*"),
    ("*Liquidation:*", "*强平价格:*"),
    ("*Number of Entries:*", "*入场次数:*"),
    ("*Number of Exits:*", "*出场次数:*"),
    ("*Order List for Trade #*", "*交易订单列表 #*"),
    ("*Average Price:*", "*平均价格:*"),
    ("*Average Entry Price:*", "*平均入场价格:*"),
    ("*Average Exit Price:*", "*平均出场价格:*"),
    ("*Order Filled:*", "*订单成交:*"),
    ("*New Total:*", "*新增总额:*"),
    ("*Total:*", "*总额:*"),
    ("*Profit:*", "*收益:*"),
    ("*Sub Profit:*", "*部分收益:*"),
    ("*Unrealized Sub Profit:*", "*部分浮动收益:*"),
    ("*Final Profit:*", "*最终收益:*"),
    ("*Cumulative Profit:*", "*累计收益:*"),
    ("*Remaining:*", "*剩余:*"),
    ("*Duration:*", "*持仓时长:*"),
    ("*Mode:*", "*模式:*"),
    ("*Exchange:*", "*交易所:*"),
    ("*Market: *", "*市场:* "),
    ("*Stake per trade:*", "*每笔投入:*"),
    ("*Max open Trades:*", "*最大持仓数:*"),
    ("*Minimum ROI:*", "*最小 ROI:*"),
    ("*Entry strategy:*", "*入场定价策略:*"),
    ("*Exit strategy:*", "*出场定价策略:*"),
    ("*Trailing stop positive:*", "*移动止损正向阈值:*"),
    ("*Trailing stop offset:*", "*移动止损偏移:*"),
    ("*Only trail above offset:*", "*仅超过偏移后移动:*"),
    ("*Position adjustment:* On", "*仓位调整:* 开启"),
    ("*Position adjustment:* Off", "*仓位调整:* 关闭"),
    ("*Max enter position adjustment:*", "*最大加仓次数:*"),
    ("*Timeframe:*", "*周期:*"),
    ("*Strategy:*", "*策略:*"),
    ("*Current state:*", "*当前状态:*"),
    ("*Version:*", "*版本:*"),
    ("*Strategy version: *", "*策略版本:* "),
    ("*Candle OHLC*:", "*K线 OHLC*:"),
    ("*ROI:* Closed long trades", "*收益率:* 已平仓多单"),
    ("*ROI:* Closed short trades", "*收益率:* 已平仓空单"),
    ("*ROI:* Closed trades", "*收益率:* 已平仓交易"),
    ("*ROI:* All long trades", "*收益率:* 全部多单"),
    ("*ROI:* All short trades", "*收益率:* 全部空单"),
    ("*ROI:* All trades", "*收益率:* 全部交易"),
    ("*Total Trade Count:*", "*总交易数:*"),
    ("*Bot started:*", "*机器人启动时间:*"),
    ("*First Trade opened:*", "*第一笔交易开仓:*"),
    ("*Showing Profit since:*", "*显示该时间后的收益:*"),
    ("*Latest Trade opened:*", "*最近交易开仓:*"),
    ("*Win / Loss:*", "*盈利 / 亏损:*"),
    ("*Winrate:*", "*胜率:*"),
    ("*Expectancy (Ratio):*", "*期望值 (比率):*"),
    ("*Avg. Duration:*", "*平均持仓时长:*"),
    ("*Best Performing:*", "*最佳交易对:*"),
    ("*Trading volume:*", "*交易量:*"),
    ("*Profit factor:*", "*盈利因子:*"),
    ("*Max Drawdown:*", "*最大回撤:*"),
    ("*Current Drawdown:*", "*当前回撤:*"),
    ("*Estimated Value (Bot managed assets only)*", "*预估价值 (仅机器人管理资产)*"),
    ("*Estimated Value*", "*预估价值*"),
    ("*Force exit canceled.*", "*强制退出已取消。*"),
    ("Last process:", "最近处理:"),
    ("Initial bot start:", "机器人首次启动:"),
    ("Last bot restart:", "机器人最近重启:"),
    ("Dry run is enabled. All trades are simulated.", "Dry-run 已启用，所有交易都是模拟交易。"),
    ("Searching for", "正在查找"),
    ("pairs to buy and sell based on", "个可买卖交易对，规则来自"),
    ("No trades yet.", "还没有交易。"),
    ("No long trades yet.", "还没有多单交易。"),
    ("No short trades yet.", "还没有空单交易。"),
    ("`No closed trade`", "`还没有已平仓交易`"),
    ("`No closed long trade`", "`还没有已平仓多单`"),
    ("`No closed short trade`", "`还没有已平仓空单`"),
    ("No open trade found.", "没有找到未平仓交易。"),
    ("Which trade?", "选择哪一笔交易？"),
    ("Which pair?", "选择哪个交易对？"),
    ("Cancel", "取消"),
    ("Force exit canceled.", "强制退出已取消。"),
    ("Force enter canceled.", "强制入场已取消。"),
    ("Manually exiting Trade", "正在手动退出交易"),
    ("Manually entering", "正在手动入场"),
    ("Trade-id not set.", "没有设置交易 ID。"),
    ("Trade ", "交易 "),
    (" not found.", " 未找到。"),
    ("Open order canceled.", "未完成订单已取消。"),
    ("Please make sure to take care of this asset on the exchange manually.",
     "请确认你已在交易所手动处理这项资产。"),
    ("No active locks.", "当前没有生效的锁定。"),
    ("Using whitelist", "正在使用白名单"),
    ("with", "包含"),
    ("Blacklist contains", "黑名单包含"),
    ("pairs", "个交易对"),
    ("Whitelist contains", "白名单包含"),
    ("Currently set market direction:", "当前市场方向:"),
    ("Successfully updated market direction", "已成功更新市场方向"),
    ("Invalid market direction provided.", "提供的市场方向无效。"),
    ("Valid market directions:", "可用市场方向:"),
    ("Invalid usage of command /marketdir.", "市场方向命令用法无效。"),
    ("Exit Signal", "出场信号"),
    ("Force Exit", "强制退出"),
    ("Emergency Exit", "紧急退出"),
    ("Trail. Stop", "移动止损"),
    ("Stoploss", "止损"),
    ("Usage:", "用法:"),
    ("Found custom-data entries:", "找到自定义数据:"),
    ("Found custom-data entry:", "找到自定义数据:"),
    ("Didn't find any custom-data entries for Trade ID:", "没有找到该交易 ID 的自定义数据:"),
    ("and Key:", "和键:"),
    ("*Key:*", "*键:*"),
    ("*Value:*", "*值:*"),
    ("*Type:*", "*类型:*"),
    ("*Created:*", "*创建时间:*"),
    ("*Updated:*", "*更新时间:*"),
    ("Message dropped because length exceeds", "消息因超过长度限制已丢弃"),
    ("maximum allowed characters:", "最大允许字符数:"),
    ("Simulated balances in Dry Mode.", "当前为 Dry-run 模式，余额为模拟值。"),
    ("Starting capital:", "初始资金:"),
    ("Available:", "可用:"),
    ("Balance:", "余额:"),
    ("Pending:", "挂单占用:"),
    ("Bot Owned:", "机器人持有:"),
    ("Est.", "预估"),
    ("Other Currencies", "其他币种"),
    ("Other Currency", "其他币种"),
    ("Day (count)", "日期 (交易数)"),
    ("Monday (count)", "周一 (交易数)"),
    ("Month (count)", "月份 (交易数)"),
    ("Profit %", "收益 %"),
    ("Trades", "交易数"),
    ("Close Date", "平仓时间"),
    ("Pair (ID L/S)", "交易对 (ID 多/空)"),
    ("Pair (ID)", "交易对 (ID)"),
    ("Profit (", "收益 ("),
    ("Total", "合计"),
    ("(incl. realized Profits)", "(包含已实现收益)"),
    ("current", "当前"),
    ("max", "最大"),
    ("total stake", "总投入"),
    ("Exit Reason", "出场原因"),
    ("Exits", "出场次数"),
    ("Wins", "盈利"),
    ("Losses", "亏损"),
    ("Avg. Duration", "平均持仓时长"),
    ("Until", "截至"),
    ("Reason", "原因"),
    ("Entry", "入场"),
    ("Exit", "出场"),
    ("Average Entry Price", "平均入场价格"),
    ("Average Exit Price", "平均出场价格"),
    ("from 1st entry rate", "相对首次入场价"),
    ("Updated:", "更新时间:"),
    ("Refresh", "刷新"),
    ("N/A", "无"),
)


class TelegramCN(Telegram):
    """Chinese Telegram wrapper with the same backend behavior as Telegram."""

    def _init_keyboard(self) -> None:
        self._keyboard: list[list[str]] = [
            ["日报", "收益", "余额"],
            ["状态", "状态表", "表现"],
            ["持仓数", "启动", "停止", "帮助"],
        ]

        cust_keyboard = self._config["telegram"].get("keyboard", [])
        if cust_keyboard:
            self._keyboard = [
                [KEYBOARD_LABELS.get(str(button), str(button)) for button in row]
                for row in cust_keyboard
            ]
            logger.info("using custom Chinese keyboard from config.json: %s", self._keyboard)

    def _init(self) -> None:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

        self._app = self._init_telegram_app()

        handles = [
            CommandHandler("status", self._status),
            CommandHandler("profit", self._profit),
            CommandHandler("balance", self._balance),
            CommandHandler("start", self._start),
            CommandHandler("stop", self._stop),
            CommandHandler(["forcesell", "forceexit", "fx"], self._force_exit),
            CommandHandler(
                ["forcebuy", "forcelong"],
                partial(self._force_enter, order_side=SignalDirection.LONG),
            ),
            CommandHandler(
                "forceshort", partial(self._force_enter, order_side=SignalDirection.SHORT)
            ),
            CommandHandler("reload_trade", self._reload_trade_from_exchange),
            CommandHandler("trades", self._trades),
            CommandHandler("delete", self._delete_trade),
            CommandHandler(["coo", "cancel_open_order"], self._cancel_open_order),
            CommandHandler("performance", self._performance),
            CommandHandler(["buys", "entries"], self._enter_tag_performance),
            CommandHandler(["sells", "exits"], self._exit_reason_performance),
            CommandHandler("mix_tags", self._mix_tag_performance),
            CommandHandler("stats", self._stats),
            CommandHandler("daily", self._daily),
            CommandHandler("weekly", self._weekly),
            CommandHandler("monthly", self._monthly),
            CommandHandler("count", self._count),
            CommandHandler("locks", self._locks),
            CommandHandler(["unlock", "delete_locks"], self._delete_locks),
            CommandHandler(["reload_config", "reload_conf"], self._reload_config),
            CommandHandler(["show_config", "show_conf"], self._show_config),
            CommandHandler(["stopbuy", "stopentry", "pause"], self._pause),
            CommandHandler("whitelist", self._whitelist),
            CommandHandler("blacklist", self._blacklist),
            CommandHandler(["blacklist_delete", "bl_delete"], self._blacklist_delete),
            CommandHandler("logs", self._logs),
            CommandHandler("health", self._health),
            CommandHandler("help", self._help),
            CommandHandler("version", self._version),
            CommandHandler("marketdir", self._changemarketdir),
            CommandHandler("order", self._order),
            CommandHandler("list_custom_data", self._list_custom_data),
            CommandHandler("tg_info", self._tg_info),
            CommandHandler("profit_long", self._profit_long),
            CommandHandler("profit_short", self._profit_short),
            MessageHandler(filters.TEXT, self._dispatch_chinese_text),
        ]
        callbacks = [
            CallbackQueryHandler(self._status_table, pattern="update_status_table"),
            CallbackQueryHandler(self._daily, pattern="update_daily"),
            CallbackQueryHandler(self._weekly, pattern="update_weekly"),
            CallbackQueryHandler(self._monthly, pattern="update_monthly"),
            CallbackQueryHandler(self._profit_long, pattern="update_profit_long"),
            CallbackQueryHandler(self._profit_short, pattern="update_profit_short"),
            CallbackQueryHandler(self._profit, pattern=r"update_profit$"),
            CallbackQueryHandler(self._balance, pattern="update_balance"),
            CallbackQueryHandler(self._performance, pattern="update_performance"),
            CallbackQueryHandler(
                self._enter_tag_performance, pattern="update_enter_tag_performance"
            ),
            CallbackQueryHandler(
                self._exit_reason_performance, pattern="update_exit_reason_performance"
            ),
            CallbackQueryHandler(self._mix_tag_performance, pattern="update_mix_tag_performance"),
            CallbackQueryHandler(self._count, pattern="update_count"),
            CallbackQueryHandler(self._force_exit_inline, pattern=r"force_exit__\S+"),
            CallbackQueryHandler(self._force_enter_inline, pattern=r"force_enter__\S+"),
        ]
        for handle in handles:
            self._app.add_handler(handle)

        for callback in callbacks:
            self._app.add_handler(callback)

        logger.info(
            "rpc.telegram_cn is listening for following commands: %s",
            [[x for x in sorted(h.commands)] for h in handles if isinstance(h, CommandHandler)],
        )
        self._loop.run_until_complete(self._startup_telegram())

    @authorized_only
    async def _dispatch_chinese_text(self, update, context: CallbackContext) -> None:
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        if not text:
            return

        parts = text.split()
        command = parts[0].lstrip("/")
        args = parts[1:]

        command_map: dict[str, tuple[Callable[..., Any], list[str] | None]] = {
            "状态": (self._status, args),
            "状态表": (self._status, ["table", *args]),
            "收益": (self._profit, args),
            "多单收益": (self._profit_long, args),
            "空单收益": (self._profit_short, args),
            "余额": (self._balance, args),
            "启动": (self._start, args),
            "停止": (self._stop, args),
            "暂停": (self._pause, args),
            "停止入场": (self._pause, args),
            "强制卖出": (self._force_exit, args),
            "强制退出": (self._force_exit, args),
            "强制买入": (partial(self._force_enter, order_side=SignalDirection.LONG), args),
            "强制做多": (partial(self._force_enter, order_side=SignalDirection.LONG), args),
            "强制做空": (partial(self._force_enter, order_side=SignalDirection.SHORT), args),
            "重载交易": (self._reload_trade_from_exchange, args),
            "交易": (self._trades, args),
            "删除交易": (self._delete_trade, args),
            "取消订单": (self._cancel_open_order, args),
            "表现": (self._performance, args),
            "入场表现": (self._enter_tag_performance, args),
            "出场表现": (self._exit_reason_performance, args),
            "标签表现": (self._mix_tag_performance, args),
            "统计": (self._stats, args),
            "日报": (self._daily, args),
            "周报": (self._weekly, args),
            "月报": (self._monthly, args),
            "持仓数": (self._count, args),
            "锁定": (self._locks, args),
            "解锁": (self._delete_locks, args),
            "重载配置": (self._reload_config, args),
            "显示配置": (self._show_config, args),
            "白名单": (self._whitelist, args),
            "黑名单": (self._blacklist, args),
            "删除黑名单": (self._blacklist_delete, args),
            "日志": (self._logs, args),
            "健康": (self._health, args),
            "帮助": (self._help, args),
            "版本": (self._version, args),
            "市场方向": (self._changemarketdir, self._normalize_market_direction_args(args)),
            "订单": (self._order, args),
            "自定义数据": (self._list_custom_data, args),
            "纸飞机信息": (self._tg_info, args),
        }

        handler_info = command_map.get(command)
        if not handler_info:
            await self._send_msg("未知指令。发送 `帮助` 查看可用中文指令。")
            return

        handler, parsed_args = handler_info
        context.args = parsed_args or []
        await handler(update=update, context=context)

    def _normalize_market_direction_args(self, args: list[str]) -> list[str]:
        mapping = {
            "做多": "long",
            "多": "long",
            "long": "long",
            "做空": "short",
            "空": "short",
            "short": "short",
            "震荡": "even",
            "均衡": "even",
            "even": "even",
            "无": "none",
            "none": "none",
        }
        return [mapping.get(arg, arg) for arg in args]

    def _format_entry_msg(self, msg: RPCEntryMsg) -> str:
        is_fill = msg["type"] in [RPCMessageType.ENTRY_FILL]
        emoji = "\N{CHECK MARK}" if is_fill else "\N{LARGE BLUE CIRCLE}"

        terminology = {
            "1_enter": "新开交易",
            "1_entered": "新开交易已成交",
            "x_enter": "正在加仓",
            "x_entered": "加仓已成交",
        }

        key = f"{'x' if msg['sub_trade'] else '1'}_{'entered' if is_fill else 'enter'}"
        wording = terminology[key]

        message = (
            f"{emoji} *{self._exchange_from_msg(msg)}:*"
            f" {wording} (#{msg['trade_id']})\n"
            f"*交易对:* `{msg['pair']}`\n"
        )
        message += self._add_analyzed_candle(msg["pair"])
        message += f"*入场标签:* `{msg['enter_tag']}`\n" if msg.get("enter_tag") else ""
        message += f"*数量:* `{round_value(msg['amount'], 8)}`\n"
        message += f"*方向:* `{msg['direction']}"
        if msg.get("leverage") and msg.get("leverage", 1.0) != 1.0:
            message += f" ({msg['leverage']:.3g}x)"
        message += "`\n"
        message += f"*开仓价格:* `{fmt_coin2(msg['open_rate'], msg['quote_currency'])}`\n"
        if msg["type"] == RPCMessageType.ENTRY and msg["current_rate"]:
            message += f"*当前价格:* `{fmt_coin2(msg['current_rate'], msg['quote_currency'])}`\n"

        profit_fiat_extra = self._format_profit_fiat(msg, "stake_amount")
        total = fmt_coin(msg["stake_amount"], msg["quote_currency"])

        message += f"*{'新增' if msg['sub_trade'] else ''}总额:* `{total}{profit_fiat_extra}`"

        return message

    def _format_profit_fiat(self, msg: dict[str, Any], key: str) -> str:
        profit_fiat_extra = ""
        if self._rpc._fiat_converter and (fiat_currency := msg.get("fiat_currency")):
            profit_fiat = self._rpc._fiat_converter.convert_amount(
                msg[key], msg["stake_currency"], fiat_currency
            )
            profit_fiat_extra = f" / {profit_fiat:.3f} {fiat_currency}"
        return profit_fiat_extra

    def _format_exit_msg(self, msg: RPCExitMsg) -> str:
        message = super()._format_exit_msg(msg)
        return self._zh_text(message)

    def _prepare_order_details(self, filled_orders: list, quote_currency: str, is_open: bool):
        lines_detail = super()._prepare_order_details(filled_orders, quote_currency, is_open)
        return [self._zh_text(line) for line in lines_detail]

    def compose_message(self, msg: RPCSendMsg) -> str | None:
        if msg["type"] == RPCMessageType.STATUS:
            return f"*状态:* `{self._zh_status(msg['status'])}`"
        if msg["type"] == RPCMessageType.WARNING:
            return f"\N{WARNING SIGN} *警告:* `{self._zh_text(msg['status'])}`"
        if msg["type"] == RPCMessageType.EXCEPTION:
            return f"\N{WARNING SIGN} *错误:* \n {self._zh_text(msg['status'])}"
        message = super().compose_message(deepcopy(msg))
        return self._zh_text(message) if message else None

    @authorized_only
    async def _help(self, update, context: CallbackContext) -> None:
        force_enter_text = (
            "*强制做多 <交易对> [价格]:* `立即买入/做多指定交易对。价格参数只对限价单有效。`\n"
        )
        if self._rpc._freqtrade.trading_mode != TradingMode.SPOT:
            force_enter_text += (
                "*强制做空 <交易对> [价格]:* `立即做空指定交易对。价格参数只对限价单有效。`\n"
            )

        message = (
            "_机器人控制_\n"
            "------------\n"
            "*启动:* `启动交易机器人`\n"
            "*暂停:* `暂停新入场，已有持仓继续正常管理`\n"
            "*停止:* `停止交易机器人`\n"
            "*停止入场:* `停止新入场，已有持仓继续正常管理`\n"
            "*强制退出 <交易ID>|all:* `不考虑盈亏，立即退出指定交易或全部交易`\n"
            f"{force_enter_text if self._config.get('force_entry_enable', False) else ''}"
            "*删除交易 <交易ID>:* `从数据库中删除指定交易`\n"
            "*重载交易 <交易ID>:* `从交易所订单重新载入交易`\n"
            "*取消订单 <交易ID>|all:* `取消交易的未完成订单`\n"
            "*白名单 [sorted] [baseonly]:* `查看当前白名单，可排序或只显示基础币种`\n"
            "*黑名单 [交易对]:* `查看黑名单，或添加一个/多个交易对到黑名单`\n"
            "*删除黑名单 [交易对]:* `从黑名单删除交易对或匹配模式`\n"
            "*重载配置:* `重新加载配置文件`\n"
            "*解锁 <交易对|锁ID>:* `解除指定交易对或锁 ID 的锁定`\n"
            "_当前状态_\n"
            "------------\n"
            "*显示配置:* `显示当前运行配置`\n"
            "*锁定:* `显示当前被锁定的交易对`\n"
            "*余额:* `显示机器人管理的资产余额`\n"
            "*余额 total:* `显示账户全部资产余额`\n"
            "*日志 [条数]:* `显示最近日志，默认 10 条`\n"
            "*持仓数:* `显示当前活跃交易数和允许交易数`\n"
            "*健康:* `显示最近处理时间和启动时间`\n"
            "*市场方向 [做多|做空|震荡|无]:* `更新或查看当前市场方向`\n"
            "*自定义数据 <交易ID> <键>:* `查看交易自定义数据`\n"
            "_统计_\n"
            "------------\n"
            "*状态 <交易ID>|状态表:* `列出未平仓交易，或以表格显示`\n"
            "*入场表现 <交易对|none>:* `显示入场标签表现`\n"
            "*出场表现 <交易对|none>:* `显示出场原因表现`\n"
            "*标签表现 <交易对|none>:* `显示入场标签 + 出场原因组合表现`\n"
            "*交易 [条数]:* `列出最近已平仓交易，默认 10 条`\n"
            "*收益 [天数]:* `显示最近 n 天已完成交易累计收益`\n"
            "*多单收益 [天数]:* `显示最近 n 天多单累计收益`\n"
            "*空单收益 [天数]:* `显示最近 n 天空单累计收益`\n"
            "*表现:* `按交易对统计已完成交易表现`\n"
            "*日报 <天数>:* `显示最近 n 天每日盈亏`\n"
            "*周报 <周数>:* `显示最近 n 周统计`\n"
            "*月报 <月数>:* `显示最近 n 月统计`\n"
            "*统计:* `显示胜负、出场原因和平均持仓时长`\n"
            "*帮助:* `显示这条帮助信息`\n"
            "*版本:* `显示版本信息`\n\n"
            "_英文 slash 命令仍然保留，例如 /status、/profit、/balance。_"
        )
        await self._send_msg(message, parse_mode=ParseMode.MARKDOWN)

    async def _update_msg(
        self,
        query: CallbackQuery,
        msg: str,
        callback_path: str = "",
        reload_able: bool = False,
        parse_mode: str = ParseMode.MARKDOWN,
    ) -> None:
        if reload_able:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("刷新", callback_data=callback_path)]]
            )
        else:
            reply_markup = InlineKeyboardMarkup([[]])
        msg = self._zh_text(msg)
        msg += f"\n更新时间: {datetime.now().ctime()}"
        if not query.message:
            return

        try:
            await query.edit_message_text(
                text=msg, parse_mode=parse_mode, reply_markup=reply_markup
            )
        except BadRequest as e:
            if "not modified" in e.message.lower():
                pass
            else:
                logger.warning("TelegramError: %s", e.message)
        except TelegramError as telegram_err:
            logger.warning("TelegramError: %s! Giving up on that message.", telegram_err.message)

    async def _send_msg(
        self,
        msg: str,
        parse_mode: str = ParseMode.MARKDOWN,
        disable_notification: bool = False,
        keyboard: list[list[InlineKeyboardButton]] | None = None,
        callback_path: str = "",
        reload_able: bool = False,
        query: CallbackQuery | None = None,
    ) -> None:
        msg = self._zh_text(msg)
        if query:
            await self._update_msg(
                query=query,
                msg=msg,
                parse_mode=parse_mode,
                callback_path=callback_path,
                reload_able=reload_able,
            )
            return
        if reload_able and self._config["telegram"].get("reload", True):
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("刷新", callback_data=callback_path)]]
            )
        elif keyboard is not None:
            reply_markup = InlineKeyboardMarkup(self._zh_inline_keyboard(keyboard))
        else:
            reply_markup = ReplyKeyboardMarkup(self._keyboard, resize_keyboard=True)
        try:
            try:
                await self._app.bot.send_message(
                    self._config["telegram"]["chat_id"],
                    text=msg,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    message_thread_id=self._config["telegram"].get("topic_id"),
                )
            except NetworkError as network_err:
                logger.warning(
                    "Telegram NetworkError: %s! Trying one more time.", network_err.message
                )
                await self._app.bot.send_message(
                    self._config["telegram"]["chat_id"],
                    text=msg,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    message_thread_id=self._config["telegram"].get("topic_id"),
                )
        except TelegramError as telegram_err:
            logger.warning("TelegramError: %s! Giving up on that message.", telegram_err.message)

    @authorized_only
    async def _changemarketdir(self, update, context: CallbackContext) -> None:
        if context.args and len(context.args) == 1:
            new_market_dir_arg = self._normalize_market_direction_args(context.args)[0]
            old_market_dir = self._rpc._get_market_direction()
            new_market_dir = None
            if new_market_dir_arg == "long":
                new_market_dir = MarketDirection.LONG
            elif new_market_dir_arg == "short":
                new_market_dir = MarketDirection.SHORT
            elif new_market_dir_arg == "even":
                new_market_dir = MarketDirection.EVEN
            elif new_market_dir_arg == "none":
                new_market_dir = MarketDirection.NONE

            if new_market_dir is not None:
                self._rpc._update_market_direction(new_market_dir)
                await self._send_msg(
                    f"市场方向已从 *{old_market_dir}* 更新为 *{new_market_dir}*。"
                )
            else:
                raise RPCException("市场方向无效。可用值: *做多, 做空, 震荡, 无*")
        elif context.args is not None and len(context.args) == 0:
            old_market_dir = self._rpc._get_market_direction()
            await self._send_msg(f"当前市场方向: *{old_market_dir}*")
        else:
            raise RPCException("用法: *市场方向 [做多 | 做空 | 震荡 | 无]*")

    def _zh_status(self, status: str) -> str:
        return STATUS_WORDS.get(status, status)

    def _zh_text(self, msg: str | None) -> str:
        if not msg:
            return ""

        translated = msg
        translated = re.sub(
            r"<b>(\d+) recent trades</b>:",
            r"<b>最近 \1 笔交易</b>:",
            translated,
        )
        translated = re.sub(
            r"<b>Daily Profit over the last (\d+) days</b>:",
            r"<b>最近 \1 天每日收益</b>:",
            translated,
        )
        translated = re.sub(
            r"<b>Weekly Profit over the last (\d+) weeks \(starting from Monday\)</b>:",
            r"<b>最近 \1 周收益 (从周一开始)</b>:",
            translated,
        )
        translated = re.sub(
            r"<b>Monthly Profit over the last (\d+) months</b>:",
            r"<b>最近 \1 月收益</b>:",
            translated,
        )
        translated = re.sub(
            r"(\d+) recent trades",
            r"最近 \1 笔交易",
            translated,
        )
        translated = re.sub(
            r"\bfrom `([^`]+)`",
            r"从 `\1`",
            translated,
        )
        translated = re.sub(
            r"\bto `([^`]+)`",
            r"到 `\1`",
            translated,
        )
        for source, target in TEXT_REPLACEMENTS:
            translated = translated.replace(source, target)
        for source, target in STATUS_WORDS.items():
            translated = translated.replace(f"`{source}`", f"`{target}`")
        return translated

    def _zh_inline_keyboard(
        self, keyboard: list[list[InlineKeyboardButton]]
    ) -> list[list[InlineKeyboardButton]]:
        return [
            [
                InlineKeyboardButton(
                    text=self._zh_text(button.text),
                    callback_data=button.callback_data,
                )
                for button in row
            ]
            for row in keyboard
        ]
