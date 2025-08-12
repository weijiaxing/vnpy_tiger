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
        # 实时检查Tiger API是否可用
        try:
            import tigeropen
            from tigeropen.tiger_open_config import TigerOpenClientConfig
        except ImportError:
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
        
        # 查询合约信息
        self.add_task(self.query_contracts)

    def init_client_config(self):
        """初始化客户端配置"""
        # 新版本Tiger API不再支持sandbox_debug参数
        self.client_config = TigerOpenClientConfig()
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
            
            # 测试行情连接
            try:
                # 使用正确的API方法测试连接
                self.quote_client.get_trading_calendar()
                self.write_log("行情接口测试成功")
            except Exception as test_e:
                self.write_log(f"行情接口测试失败，但连接已建立: {str(test_e)}")
                # 即使测试失败，行情客户端可能仍然可用
                
        except Exception as e:
            self.write_log(f"行情接口连接失败: {str(e)}")

    def connect_trade(self):
        """连接交易服务"""
        try:
            self.trade_client = TradeClient(self.client_config)
            self.write_log("交易接口连接成功")
            
            # 立即查询账户和持仓信息
            self.add_task(self.query_account)
            self.add_task(self.query_position)
            
            # 测试交易连接
            try:
                # 通过查询资产来测试连接
                assets = self.trade_client.get_assets()
                if assets:
                    self.write_log("交易接口测试成功")
                else:
                    self.write_log("交易接口连接成功，但未获取到资产数据")
            except Exception as test_e:
                self.write_log(f"交易接口测试失败，但连接已建立: {str(test_e)}")
                # 即使测试失败，交易客户端可能仍然可用
                
        except Exception as e:
            self.write_log(f"交易接口连接失败: {str(e)}")

    def connect_push(self):
        """连接推送服务"""
        try:
            if not TIGER_AVAILABLE:
                self.write_log("Tiger API不可用，跳过推送连接")
                return
                
            # 检查是否有推送配置
            if not hasattr(self.client_config, 'socket_host_port'):
                self.write_log("推送服务配置不可用，跳过推送连接")
                return
                
            protocol, host, port = self.client_config.socket_host_port
            self.push_client = PushClient(host, port, (protocol == "ssl"))
            
            # 设置回调函数
            self.push_client.quote_changed = self.on_quote_change
            self.push_client.asset_changed = self.on_asset_change
            self.push_client.position_changed = self.on_position_change
            self.push_client.order_changed = self.on_order_change
            self.push_client.connect_callback = self.on_push_connected
            
            # 连接推送服务
            self.push_client.connect(
                self.client_config.tiger_id, self.client_config.private_key)
            self.write_log("推送接口连接成功")
        except Exception as e:
            self.write_log(f"推送接口连接失败: {str(e)}")
            # 推送失败不影响基本功能，继续运行

    def close(self) -> None:
        """关闭连接"""
        self.active = False
        
        if self.query_thread and self.query_thread.is_alive():
            self.query_thread.join()

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        if not self.quote_client:
            self.write_log("行情客户端未连接，无法订阅行情")
            return
        
        try:
            # 动态创建合约（如果不存在）
            self.get_contract(req.symbol, req.exchange)
            
            # 添加到订阅列表
            self.subscribed_symbols.add(req.symbol)
            
            # 如果推送客户端已连接，立即订阅
            if self.push_connected and self.push_client:
                tiger_symbol = f"{req.symbol}"
                self.push_client.subscribe_quote([tiger_symbol])
                self.write_log(f"订阅行情成功: {req.vt_symbol}")
            else:
                self.write_log(f"行情订阅已记录，等待推送连接: {req.vt_symbol}")
                
        except Exception as e:
            self.write_log(f"订阅行情失败: {str(e)}")

    def send_order(self, req: OrderRequest) -> str:
        """发送订单"""
        if not self.trade_client:
            self.write_log("交易客户端未连接，无法发送订单")
            return ""
        
        # 动态创建合约（如果不存在）
        self.get_contract(req.symbol, req.exchange)
        
        local_id = self.get_new_local_id()
        order = req.create_order_data(local_id, self.gateway_name)
        
        try:
            # 创建Tiger订单对象 - 使用正确的构造方法
            from tigeropen.trade.domain.order import Order
            
            # Tiger Order需要必要的参数
            tiger_order = Order(
                account=self.account,
                symbol=req.symbol,
                action=DIRECTION_VT2TIGER.get(req.direction, "BUY"),
                order_type=ORDERTYPE_VT2TIGER.get(req.type, "LMT"),
                quantity=int(req.volume)
            )
            
            # 设置限价单价格
            if req.type == OrderType.LIMIT:
                tiger_order.limit_price = float(req.price)
            
            # 发送订单到Tiger
            result = self.trade_client.place_order(tiger_order)
            
            if result:
                order.status = Status.SUBMITTING
                self.on_order(order)
                self.write_log(f"订单提交成功: {req.vt_symbol} {req.direction.value} {req.volume}@{req.price}")
                return order.vt_orderid
            else:
                order.status = Status.REJECTED
                self.on_order(order)
                self.write_log(f"订单提交失败: {req.vt_symbol}")
                return ""
                
        except Exception as e:
            order.status = Status.REJECTED
            self.on_order(order)
            self.write_log(f"订单提交异常: {str(e)}")
            return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """撤销订单"""
        if not self.trade_client:
            self.write_log("交易客户端未连接，无法撤销订单")
            return
        
        try:
            # 查找Tiger订单ID
            tiger_order_id = self.ID_VT2TIGER.get(req.orderid)
            if not tiger_order_id:
                self.write_log(f"未找到对应的Tiger订单ID: {req.orderid}")
                return
            
            # 撤销订单
            result = self.trade_client.cancel_order(tiger_order_id)
            
            if result:
                self.write_log(f"撤销订单成功: {req.orderid}")
            else:
                self.write_log(f"撤销订单失败: {req.orderid}")
                
        except Exception as e:
            self.write_log(f"撤销订单异常: {str(e)}")

    def query_account(self) -> None:
        """查询账户"""
        if not self.trade_client:
            return
        
        try:
            # 查询真实账户资产
            assets = self.trade_client.get_assets()
            if assets:
                for asset in assets:
                    # 获取账户信息
                    account_id = getattr(asset, 'account', self.account)
                    
                    # 获取余额信息
                    balance = 0.0
                    frozen = 0.0
                    
                    if hasattr(asset, 'summary'):
                        summary = asset.summary
                        # 获取净资产作为余额
                        raw_balance = getattr(summary, 'net_liquidation', 0) or \
                                    getattr(summary, 'total_cash', 0) or \
                                    getattr(summary, 'cash', 0) or 0
                        
                        # 修复浮点数精度问题，四舍五入到美分
                        balance = round(float(raw_balance), 2)
                        
                        # 获取冻结资金
                        raw_frozen = getattr(summary, 'init_margin_req', 0) or \
                                   getattr(summary, 'initial_margin', 0) or 0
                        frozen = round(float(raw_frozen), 2)
                    
                    # 创建账户数据
                    account = AccountData(
                        accountid=account_id,
                        balance=balance,
                        frozen=frozen,
                        gateway_name=self.gateway_name
                    )
                    self.on_account(account)
                    
                    # 格式化显示美元金额
                    self.write_log(f"账户查询成功: 账户 {account_id}, 余额 ${balance:.2f}, 冻结 ${frozen:.2f}")
            else:
                self.write_log("未获取到账户资产信息")
        except Exception as e:
            self.write_log(f"查询账户失败: {str(e)}")
            # 如果API调用失败，显示基本账户信息
            account = AccountData(
                accountid=self.account,
                balance=0.0,
                frozen=0.0,
                gateway_name=self.gateway_name
            )
            self.on_account(account)

    def query_position(self) -> None:
        """查询持仓"""
        if not self.trade_client:
            return
        
        try:
            # 查询真实持仓信息
            positions = self.trade_client.get_positions()
            
            if positions:
                for pos in positions:
                    # 解析持仓数据
                    symbol = getattr(pos, 'symbol', '')
                    quantity = float(getattr(pos, 'quantity', 0))
                    
                    if quantity == 0:
                        continue  # 跳过零持仓
                    
                    # 确定交易所
                    market = getattr(pos, 'market', 'US')
                    exchange = EXCHANGE_TIGER2VT.get(market, Exchange.NASDAQ)
                    
                    # 确定方向
                    direction = Direction.LONG if quantity > 0 else Direction.SHORT
                    
                    # 创建持仓数据
                    position = PositionData(
                        symbol=symbol,
                        exchange=exchange,
                        direction=direction,
                        volume=abs(quantity),
                        frozen=0.0,
                        price=float(getattr(pos, 'average_cost', 0)),
                        pnl=float(getattr(pos, 'unrealized_pnl', 0)),
                        gateway_name=self.gateway_name
                    )
                    self.on_position(position)
                    
                    # 记录持仓信息
                    pnl_str = f"${position.pnl:.2f}" if position.pnl != 0 else "$0.00"
                    self.write_log(f"持仓: {symbol} {direction.value} {abs(quantity)} @ ${position.price:.2f}, 盈亏: {pnl_str}")
                
                self.write_log("持仓查询完成")
            else:
                self.write_log("当前无持仓")
                
        except Exception as e:
            self.write_log(f"查询持仓失败: {str(e)}")
            import traceback
            self.write_log(f"持仓查询详细错误: {traceback.format_exc()}")

    def get_new_local_id(self) -> str:
        """生成新的本地订单ID"""
        self.local_id += 1
        return str(self.local_id)

    def on_push_connected(self):
        """推送连接成功回调"""
        self.push_connected = True
        self.write_log("推送服务连接成功")
        
        # 订阅推送
        if self.push_client:
            try:
                self.push_client.subscribe_asset()
                self.push_client.subscribe_position()
                self.push_client.subscribe_order()
                
                # 订阅之前记录的行情
                if self.subscribed_symbols:
                    symbols_list = list(self.subscribed_symbols)
                    self.push_client.subscribe_quote(symbols_list)
                    self.write_log(f"订阅 {len(symbols_list)} 个行情推送")
                
                self.write_log("推送订阅设置完成")
            except Exception as e:
                self.write_log(f"推送订阅设置失败: {str(e)}")

    def on_quote_change(self, tiger_symbol: str, data: list, trading: bool):
        """行情推送回调"""
        try:
            # 这里可以处理实时行情推送
            self.write_log(f"收到行情推送: {tiger_symbol}")
        except Exception as e:
            self.write_log(f"处理行情推送异常: {str(e)}")

    def on_asset_change(self, tiger_account: str, data: list):
        """资产变化推送回调"""
        try:
            self.write_log(f"收到资产变化推送: {tiger_account}")
            # 重新查询账户信息
            self.add_task(self.query_account)
        except Exception as e:
            self.write_log(f"处理资产推送异常: {str(e)}")

    def on_position_change(self, tiger_account: str, data: list):
        """持仓变化推送回调"""
        try:
            self.write_log(f"收到持仓变化推送: {tiger_account}")
            # 重新查询持仓信息
            self.add_task(self.query_position)
        except Exception as e:
            self.write_log(f"处理持仓推送异常: {str(e)}")

    def on_order_change(self, tiger_account: str, data: list):
        """订单变化推送回调"""
        try:
            self.write_log(f"收到订单变化推送: {tiger_account}")
            # 这里可以处理订单状态变化
        except Exception as e:
            self.write_log(f"处理订单推送异常: {str(e)}")

    def query_contracts(self) -> None:
        """初始化合约查询系统"""
        if not self.quote_client:
            return
        
        try:
            self.write_log("合约查询系统已就绪 - 支持动态查询任意美股/ETF合约")
            self.write_log("用户可以直接输入任何股票代码进行交易，系统会自动创建合约")
            
        except Exception as e:
            self.write_log(f"合约查询系统初始化失败: {str(e)}")

    def get_contract(self, symbol: str, exchange: Exchange = Exchange.NASDAQ) -> ContractData:
        """动态获取或创建合约"""
        vt_symbol = f"{symbol}.{exchange.value}"
        
        # 如果合约已存在，直接返回
        if vt_symbol in self.contracts:
            return self.contracts[vt_symbol]
        
        # 动态创建新合约
        try:
            contract = ContractData(
                symbol=symbol,
                exchange=exchange,
                name=symbol,
                product=Product.EQUITY,
                size=1,
                pricetick=0.01,
                gateway_name=self.gateway_name
            )
            
            # 缓存合约并推送给系统
            self.contracts[vt_symbol] = contract
            self.on_contract(contract)
            
            self.write_log(f"动态创建合约: {symbol} ({exchange.value})")
            return contract
            
        except Exception as e:
            self.write_log(f"创建合约 {symbol} 失败: {str(e)}")
            return None

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """查询历史数据"""
        history = []
        self.write_log(f"查询历史数据: {req.vt_symbol}")
        
        if not self.quote_client:
            return history
        
        try:
            # 这里可以实现历史数据查询
            # 由于Tiger API的历史数据接口比较复杂，暂时返回空列表
            self.write_log("历史数据查询功能待完善")
        except Exception as e:
            self.write_log(f"查询历史数据失败: {str(e)}")
        
        return history