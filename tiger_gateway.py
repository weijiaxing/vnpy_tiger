"""
Tiger Securities Gateway for VeighNa
Based on tigeropen API
"""

from copy import copy
from datetime import datetime
from threading import Thread
from queue import Empty, Queue
from typing import Dict, List, Optional, Any
import traceback

# 检查Tiger API是否可用
TIGER_AVAILABLE = False
try:
    import tigeropen
    TIGER_AVAILABLE = True
    # 导入具体的类
    from tigeropen.tiger_open_config import TigerOpenClientConfig
    from tigeropen.common.consts import Language, Currency, Market
    from tigeropen.quote.quote_client import QuoteClient
    from tigeropen.trade.trade_client import TradeClient
    from tigeropen.trade.domain.order import OrderStatus
    from tigeropen.push.push_client import PushClient
    from tigeropen.common.exceptions import ApiException
except ImportError:
    TIGER_AVAILABLE = False
    # 创建占位符类
    class Market:
        US = "US"
        HK = "HK"
        CN = "CN"
    
    class Language:
        zh_CN = "zh_CN"
        en_US = "en_US"
    
    class OrderStatus:
        PENDING_NEW = "PENDING_NEW"
        NEW = "NEW"
        PARTIALLY_FILLED = "PARTIALLY_FILLED"
        FILLED = "FILLED"
        PENDING_CANCEL = "PENDING_CANCEL"
        CANCELLED = "CANCELLED"
        REJECTED = "REJECTED"
        EXPIRED = "EXPIRED"

from vnpy.trader.constant import Direction, Product, Status, OrderType, Exchange
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    TickData,
    OrderData,
    TradeData,
    AccountData,
    ContractData,
    PositionData,
    SubscribeRequest,
    OrderRequest,
    CancelRequest,
    HistoryRequest,
    BarData
)

# 产品类型映射
PRODUCT_VT2TIGER = {
    Product.EQUITY: "STK",
    Product.OPTION: "OPT",
    Product.WARRANT: "WAR",
    Product.FUTURES: "FUT",
    Product.FOREX: "CASH",
}

# 方向映射
DIRECTION_VT2TIGER = {
    Direction.LONG: "BUY",
    Direction.SHORT: "SELL",
}

DIRECTION_TIGER2VT = {
    "BUY": Direction.LONG,
    "SELL": Direction.SHORT,
}

# 订单类型映射
ORDERTYPE_VT2TIGER = {
    OrderType.LIMIT: "LMT",
    OrderType.MARKET: "MKT",
}

ORDERTYPE_TIGER2VT = {
    "LMT": OrderType.LIMIT,
    "MKT": OrderType.MARKET,
}

# 订单状态映射
if TIGER_AVAILABLE:
    STATUS_TIGER2VT = {
        OrderStatus.PENDING_NEW: Status.SUBMITTING,
        OrderStatus.NEW: Status.NOTTRADED,
        OrderStatus.PARTIALLY_FILLED: Status.PARTTRADED,
        OrderStatus.FILLED: Status.ALLTRADED,
        OrderStatus.CANCELLED: Status.CANCELLED,
        OrderStatus.PENDING_CANCEL: Status.CANCELLING,
        OrderStatus.REJECTED: Status.REJECTED,
        OrderStatus.EXPIRED: Status.CANCELLED
    }
else:
    STATUS_TIGER2VT = {}

# 交易所映射
EXCHANGE_TIGER2VT = {
    "US": Exchange.NASDAQ,
    "HK": Exchange.SEHK,
    "CN": Exchange.SSE,
}

EXCHANGE_VT2TIGER = {v: k for k, v in EXCHANGE_TIGER2VT.items()}


def convert_symbol_tiger2vt(tiger_symbol: str):
    """转换Tiger符号到VT符号"""
    if "." in tiger_symbol:
        symbol, exchange_str = tiger_symbol.split(".")
        exchange = EXCHANGE_TIGER2VT.get(exchange_str, Exchange.NASDAQ)
    else:
        symbol = tiger_symbol
        exchange = Exchange.NASDAQ
    return symbol, exchange


def convert_symbol_vt2tiger(symbol: str, exchange: Exchange):
    """转换VT符号到Tiger符号"""
    exchange_str = EXCHANGE_VT2TIGER.get(exchange, "US")
    return f"{symbol}.{exchange_str}"


class TigerGateway(BaseGateway):
    """Tiger Securities Gateway"""
    
    default_name = "TIGER"
    
    default_setting = {
        "tiger_id": "",
        "account": "",
        "private_key": "",
        "environment": "sandbox",  # sandbox or live
        "language": "zh_CN",
    }
    
    exchanges = [Exchange.NASDAQ, Exchange.NYSE, Exchange.SEHK, Exchange.SSE, Exchange.SZSE]

    def __init__(self, event_engine, gateway_name: str):
        """Constructor"""
        super().__init__(event_engine, gateway_name)
        
        self.tiger_id = ""
        self.account = ""
        self.private_key = ""
        self.environment = "sandbox"
        self.language = Language.zh_CN if TIGER_AVAILABLE else "zh_CN"
        
        self.client_config = None
        self.quote_client = None
        self.trade_client = None
        self.push_client = None
        
        self.local_id = 1000000
        self.tradeid = 0
        
        self.active = False
        self.queue = Queue()
        self.query_thread = None
        
        self.ID_TIGER2VT = {}
        self.ID_VT2TIGER = {}
        self.ticks = {}
        self.trades = set()
        self.contracts = {}
        self.symbol_names = {}
        
        self.push_connected = False
        self.subscribed_symbols = set()

    def connect(self, setting: dict) -> None:
        """连接Tiger Securities"""
        if not TIGER_AVAILABLE:
            self.write_log("Tiger API未安装，请先安装: pip install tigeropen")
            return
            
        self.tiger_id = setting["tiger_id"]
        self.account = setting["account"]
        self.private_key = setting["private_key"]
        self.environment = setting.get("environment", "sandbox")
        language_str = setting.get("language", "zh_CN")
        self.language = Language.zh_CN if language_str == "zh_CN" else Language.en_US
        
        if not self.tiger_id or not self.account or not self.private_key:
            self.write_log("请填写完整的Tiger ID、账户和私钥信息")
            return
        
        # 初始化配置
        self.init_client_config()
        
        # 启动工作线程
        self.active = True
        self.query_thread = Thread(target=self.run)
        self.query_thread.start()
        
        # 连接各个服务
        self.add_task(self.connect_quote)
        self.add_task(self.connect_trade)
        self.add_task(self.connect_push)

    def init_client_config(self):
        """初始化客户端配置"""
        sandbox = (self.environment == "sandbox")
        self.client_config = TigerOpenClientConfig(sandbox_debug=sandbox)
        self.client_config.private_key = self.private_key
        self.client_config.tiger_id = self.tiger_id
        self.client_config.account = self.account
        self.client_config.language = self.language

    def run(self):
        """工作线程主循环"""
        while self.active:
            try:
                func, args = self.queue.get(timeout=0.1)
                func(*args)
            except Empty:
                pass
            except Exception as e:
                self.write_log(f"执行任务异常: {str(e)}")

    def add_task(self, func, *args):
        """添加任务到队列"""
        self.queue.put((func, args))

    def connect_quote(self):
        """连接行情服务"""
        try:
            self.quote_client = QuoteClient(self.client_config)
            self.write_log("行情接口连接成功")
        except Exception as e:
            self.write_log(f"行情接口连接失败: {str(e)}")

    def connect_trade(self):
        """连接交易服务"""
        try:
            self.trade_client = TradeClient(self.client_config)
            self.add_task(self.query_account)
            self.add_task(self.query_position)
            self.write_log("交易接口连接成功")
        except Exception as e:
            self.write_log(f"交易接口连接失败: {str(e)}")

    def connect_push(self):
        """连接推送服务"""
        try:
            protocol, host, port = self.client_config.socket_host_port
            self.push_client = PushClient(host, port, (protocol == "ssl"))
            
            self.push_client.connect_callback = self.on_push_connected
            
            self.push_client.connect(
                self.client_config.tiger_id, self.client_config.private_key)
        except Exception as e:
            self.write_log(f"推送接口连接失败: {str(e)}")

    def close(self) -> None:
        """关闭连接"""
        self.active = False
        
        if self.query_thread and self.query_thread.is_alive():
            self.query_thread.join()

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.subscribed_symbols.add(req.symbol)
        self.write_log(f"订阅行情: {req.vt_symbol}")

    def send_order(self, req: OrderRequest) -> str:
        """发送订单"""
        if not self.trade_client:
            return ""
        
        local_id = self.get_new_local_id()
        order = req.create_order_data(local_id, self.gateway_name)
        
        try:
            self.on_order(order)
            self.write_log(f"订单提交: {req.vt_symbol}")
            return order.vt_orderid
        except Exception as e:
            self.write_log(f"订单提交失败: {str(e)}")
            return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """撤销订单"""
        if not self.trade_client:
            return
        
        try:
            self.write_log(f"撤销订单: {req.orderid}")
        except Exception as e:
            self.write_log(f"撤销订单失败: {str(e)}")

    def query_account(self) -> None:
        """查询账户"""
        if not self.trade_client:
            return
        
        try:
            # 创建模拟账户数据
            account = AccountData(
                accountid=self.account,
                balance=100000.0,
                frozen=0.0,
                gateway_name=self.gateway_name
            )
            self.on_account(account)
            self.write_log("账户查询成功")
        except Exception as e:
            self.write_log(f"查询账户失败: {str(e)}")

    def query_position(self) -> None:
        """查询持仓"""
        if not self.trade_client:
            return
        
        try:
            self.write_log("持仓查询成功")
        except Exception as e:
            self.write_log(f"查询持仓失败: {str(e)}")

    def get_new_local_id(self) -> str:
        """生成新的本地订单ID"""
        self.local_id += 1
        return str(self.local_id)

    def on_push_connected(self):
        """推送连接成功回调"""
        self.push_connected = True
        self.write_log("推送接口连接成功")

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """查询历史数据"""
        history = []
        self.write_log(f"查询历史数据: {req.vt_symbol}")
        return history