"""
Tiger Securities Gateway for VeighNa
"""

import sys
from copy import copy
from datetime import datetime, timezone
from threading import Thread
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal

from tigeropen.common.consts import Language, Market, Currency
from tigeropen.common.util.signature_utils import read_private_key
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.trade.trade_client import TradeClient
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.common.consts import service_types
from tigeropen.trade.domain.order import Order
from tigeropen.quote.domain.subscribe_param import SubscribeParam
from tigeropen.common.consts import OrderStatus as TigerOrderStatus
from tigeropen.common.consts import ActionType, OrderType as TigerOrderType
from tigeropen.common.consts import TimeInForce

from vnpy.event import Event, EventEngine
from vnpy.trader.constant import (
    Direction,
    Exchange,
    Product,
    Status,
    OrderType,
    Offset,
    Interval
)
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    TickData,
    OrderData,
    TradeData,
    PositionData,
    AccountData,
    ContractData,
    OrderRequest,
    CancelRequest,
    SubscribeRequest,
    HistoryRequest,
    BarData
)


# 交易所映射
EXCHANGE_TIGER2VT = {
    Market.US: Exchange.NASDAQ,
    Market.HK: Exchange.SEHK,
    Market.CN: Exchange.SSE,
}

EXCHANGE_VT2TIGER = {v: k for k, v in EXCHANGE_TIGER2VT.items()}

# 方向映射
DIRECTION_TIGER2VT = {
    ActionType.BUY: Direction.LONG,
    ActionType.SELL: Direction.SHORT,
}

DIRECTION_VT2TIGER = {v: k for k, v in DIRECTION_TIGER2VT.items()}

# 订单类型映射
ORDERTYPE_TIGER2VT = {
    TigerOrderType.MKT: OrderType.MARKET,
    TigerOrderType.LMT: OrderType.LIMIT,
    TigerOrderType.STP: OrderType.STOP,
    TigerOrderType.STP_LMT: OrderType.STOP,
}

ORDERTYPE_VT2TIGER = {
    OrderType.MARKET: TigerOrderType.MKT,
    OrderType.LIMIT: TigerOrderType.LMT,
    OrderType.STOP: TigerOrderType.STP,
}

# 订单状态映射
STATUS_TIGER2VT = {
    TigerOrderStatus.PENDING_NEW: Status.SUBMITTING,
    TigerOrderStatus.NEW: Status.NOTTRADED,
    TigerOrderStatus.PARTIALLY_FILLED: Status.PARTTRADED,
    TigerOrderStatus.FILLED: Status.ALLTRADED,
    TigerOrderStatus.PENDING_CANCEL: Status.CANCELLING,
    TigerOrderStatus.CANCELLED: Status.CANCELLED,
    TigerOrderStatus.REJECTED: Status.REJECTED,
    TigerOrderStatus.EXPIRED: Status.CANCELLED,
}


class TigerGateway(BaseGateway):
    """
    VeighNa Gateway for Tiger Securities.
    """

    default_name = "TIGER"

    default_setting = {
        "tiger_id": "",
        "account": "",
        "private_key_path": "",
        "tiger_public_key_path": "",
        "environment": "sandbox",  # sandbox or live
        "language": "zh_CN",
    }

    exchanges = [Exchange.NASDAQ, Exchange.NYSE, Exchange.SEHK, Exchange.SSE, Exchange.SZSE]

    def __init__(self, event_engine: EventEngine, gateway_name: str):
        """Constructor"""
        super().__init__(event_engine, gateway_name)

        self.trade_client: Optional[TradeClient] = None
        self.quote_client: Optional[QuoteClient] = None
        
        self.subscribed: Dict[str, SubscribeRequest] = {}
        self.order_count = 0
        
        # 数据缓存
        self.orders: Dict[str, OrderData] = {}
        self.trades: Dict[str, TradeData] = {}
        
        # 查询线程
        self.query_thread: Optional[Thread] = None
        self.active = False

    def connect(self, setting: dict) -> None:
        """连接Tiger Securities"""
        tiger_id = setting["tiger_id"]
        account = setting["account"]
        private_key_path = setting["private_key_path"]
        tiger_public_key_path = setting["tiger_public_key_path"]
        environment = setting.get("environment", "sandbox")
        language = setting.get("language", "zh_CN")

        if not tiger_id or not account:
            self.write_log("请填写Tiger ID和账户信息")
            return

        try:
            # 读取私钥
            private_key = read_private_key(private_key_path)
            
            # 配置Tiger Open API
            config = TigerOpenClientConfig(
                tiger_id=tiger_id,
                account=account,
                private_key=private_key,
                tiger_public_key_path=tiger_public_key_path,
                environment=environment,
                language=Language.zh_CN if language == "zh_CN" else Language.en_US
            )
            
            # 创建交易和行情客户端
            self.trade_client = TradeClient(config)
            self.quote_client = QuoteClient(config)
            
            self.write_log("Tiger Securities API连接成功")
            
            # 启动查询线程
            self.active = True
            self.query_thread = Thread(target=self.query_data)
            self.query_thread.start()
            
            # 查询基础信息
            self.query_account()
            self.query_position()
            self.query_orders()
            
        except Exception as e:
            self.write_log(f"连接失败：{str(e)}")

    def close(self) -> None:
        """关闭连接"""
        self.active = False
        
        if self.query_thread and self.query_thread.is_alive():
            self.query_thread.join()

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        if not self.quote_client:
            return
            
        tiger_symbol = f"{req.symbol}"
        market = EXCHANGE_VT2TIGER.get(req.exchange)
        
        if not market:
            self.write_log(f"不支持的交易所：{req.exchange}")
            return
            
        try:
            # 订阅实时行情
            param = SubscribeParam()
            param.symbols = [tiger_symbol]
            param.market = market
            param.quote_types = [service_types.QUOTE_REAL_TIME]
            
            self.quote_client.subscribe(param)
            self.subscribed[req.vt_symbol] = req
            
            self.write_log(f"订阅行情成功：{req.vt_symbol}")
            
        except Exception as e:
            self.write_log(f"订阅行情失败：{str(e)}")

    def send_order(self, req: OrderRequest) -> str:
        """发送订单"""
        if not self.trade_client:
            return ""
            
        # 生成本地订单号
        self.order_count += 1
        orderid = str(self.order_count)
        
        # 创建Tiger订单
        order = Order()
        order.account = self.trade_client.account
        order.symbol = req.symbol
        order.market = EXCHANGE_VT2TIGER.get(req.exchange)
        order.action = DIRECTION_VT2TIGER.get(req.direction)
        order.order_type = ORDERTYPE_VT2TIGER.get(req.type, TigerOrderType.LMT)
        order.quantity = int(req.volume)
        
        if req.type == OrderType.LIMIT:
            order.limit_price = float(req.price)
        elif req.type == OrderType.STOP:
            order.aux_price = float(req.price)
            
        order.time_in_force = TimeInForce.DAY
        
        try:
            # 发送订单
            result = self.trade_client.place_order(order)
            
            if result and hasattr(result, 'id'):
                tiger_orderid = str(result.id)
                
                # 创建OrderData对象
                order_data = req.create_order_data(orderid, self.gateway_name)
                order_data.status = Status.SUBMITTING
                
                self.orders[orderid] = order_data
                self.on_order(order_data)
                
                self.write_log(f"订单发送成功：{req.vt_symbol} {req.direction.value} {req.volume}@{req.price}")
                return order_data.vt_orderid
            else:
                self.write_log(f"订单发送失败：{req.vt_symbol}")
                return ""
                
        except Exception as e:
            self.write_log(f"订单发送异常：{str(e)}")
            return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """撤销订单"""
        if not self.trade_client:
            return
            
        try:
            # 这里需要根据实际的Tiger API来撤销订单
            # 由于示例中没有具体的撤单方法，这里使用占位符
            self.write_log(f"撤销订单：{req.orderid}")
            
        except Exception as e:
            self.write_log(f"撤销订单失败：{str(e)}")

    def query_account(self) -> None:
        """查询账户资金"""
        if not self.trade_client:
            return
            
        try:
            # 查询账户信息
            assets = self.trade_client.get_assets()
            
            if assets:
                for asset in assets:
                    account = AccountData(
                        accountid=asset.account,
                        balance=float(asset.summary.net_liquidation or 0),
                        frozen=float(asset.summary.init_margin_req or 0),
                        gateway_name=self.gateway_name
                    )
                    self.on_account(account)
                    
        except Exception as e:
            self.write_log(f"查询账户失败：{str(e)}")

    def query_position(self) -> None:
        """查询持仓"""
        if not self.trade_client:
            return
            
        try:
            # 查询持仓信息
            positions = self.trade_client.get_positions()
            
            if positions:
                for pos in positions:
                    exchange = EXCHANGE_TIGER2VT.get(pos.market, Exchange.NASDAQ)
                    
                    position = PositionData(
                        symbol=pos.symbol,
                        exchange=exchange,
                        direction=Direction.LONG if pos.quantity > 0 else Direction.SHORT,
                        volume=abs(float(pos.quantity or 0)),
                        frozen=0.0,
                        price=float(pos.average_cost or 0),
                        pnl=float(pos.unrealized_pnl or 0),
                        gateway_name=self.gateway_name
                    )
                    self.on_position(position)
                    
        except Exception as e:
            self.write_log(f"查询持仓失败：{str(e)}")

    def query_orders(self) -> None:
        """查询订单"""
        if not self.trade_client:
            return
            
        try:
            # 查询订单信息
            orders = self.trade_client.get_orders()
            
            if orders:
                for tiger_order in orders:
                    exchange = EXCHANGE_TIGER2VT.get(tiger_order.market, Exchange.NASDAQ)
                    
                    order = OrderData(
                        orderid=str(tiger_order.id),
                        symbol=tiger_order.symbol,
                        exchange=exchange,
                        price=float(tiger_order.limit_price or 0),
                        volume=float(tiger_order.quantity or 0),
                        type=ORDERTYPE_TIGER2VT.get(tiger_order.order_type, OrderType.LIMIT),
                        direction=DIRECTION_TIGER2VT.get(tiger_order.action, Direction.LONG),
                        traded=float(tiger_order.filled or 0),
                        status=STATUS_TIGER2VT.get(tiger_order.status, Status.SUBMITTING),
                        datetime=datetime.now(),
                        gateway_name=self.gateway_name
                    )
                    self.on_order(order)
                    
        except Exception as e:
            self.write_log(f"查询订单失败：{str(e)}")

    def query_data(self) -> None:
        """查询数据主循环"""
        while self.active:
            try:
                # 定期查询账户和持仓信息
                self.query_account()
                self.query_position()
                self.query_orders()
                
                # 处理行情推送
                self.process_quote_data()
                
            except Exception as e:
                self.write_log(f"查询数据异常：{str(e)}")
                
            # 等待5秒后继续查询
            import time
            time.sleep(5)

    def process_quote_data(self) -> None:
        """处理行情数据"""
        if not self.quote_client or not self.subscribed:
            return
            
        try:
            # 获取实时行情数据
            for vt_symbol, req in self.subscribed.items():
                market = EXCHANGE_VT2TIGER.get(req.exchange)
                if not market:
                    continue
                    
                # 获取最新行情
                quotes = self.quote_client.get_market_data([req.symbol], market=market)
                
                if quotes:
                    for quote in quotes:
                        tick = TickData(
                            symbol=quote.symbol,
                            exchange=req.exchange,
                            datetime=datetime.now(timezone.utc),
                            name=quote.symbol,
                            last_price=float(quote.latest_price or 0),
                            volume=float(quote.volume or 0),
                            turnover=float(quote.amount or 0),
                            open_price=float(quote.open or 0),
                            high_price=float(quote.high or 0),
                            low_price=float(quote.low or 0),
                            pre_close=float(quote.prev_close or 0),
                            bid_price_1=float(quote.bid_price or 0),
                            ask_price_1=float(quote.ask_price or 0),
                            bid_volume_1=float(quote.bid_size or 0),
                            ask_volume_1=float(quote.ask_size or 0),
                            gateway_name=self.gateway_name
                        )
                        self.on_tick(tick)
                        
        except Exception as e:
            self.write_log(f"处理行情数据异常：{str(e)}")

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """查询历史数据"""
        history = []
        
        if not self.quote_client:
            return history
            
        try:
            market = EXCHANGE_VT2TIGER.get(req.exchange)
            if not market:
                self.write_log(f"不支持的交易所：{req.exchange}")
                return history
                
            # 转换时间间隔
            period_map = {
                Interval.MINUTE: "1min",
                Interval.HOUR: "60min", 
                Interval.DAILY: "day",
                Interval.WEEKLY: "week",
            }
            
            period = period_map.get(req.interval, "day")
            
            # 获取历史K线数据
            bars = self.quote_client.get_bars(
                symbols=[req.symbol],
                market=market,
                period=period,
                begin_time=req.start.strftime("%Y-%m-%d"),
                end_time=req.end.strftime("%Y-%m-%d")
            )
            
            if bars:
                for bar in bars:
                    bar_data = BarData(
                        symbol=req.symbol,
                        exchange=req.exchange,
                        datetime=datetime.strptime(bar.time, "%Y-%m-%d %H:%M:%S"),
                        interval=req.interval,
                        volume=float(bar.volume or 0),
                        turnover=float(bar.amount or 0),
                        open_price=float(bar.open or 0),
                        high_price=float(bar.high or 0),
                        low_price=float(bar.low or 0),
                        close_price=float(bar.close or 0),
                        gateway_name=self.gateway_name
                    )
                    history.append(bar_data)
                    
            self.write_log(f"获取历史数据成功：{req.vt_symbol} {len(history)}条")
            
        except Exception as e:
            self.write_log(f"查询历史数据失败：{str(e)}")
            
        return history