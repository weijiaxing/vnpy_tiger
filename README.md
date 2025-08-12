# VeighNa Tiger Securities Gateway

## 简介

vnpy_tiger是为VeighNa量化交易平台开发的老虎证券交易接口。

## 功能特点

- 支持美股、港股、A股交易
- 实时行情订阅
- 订单管理（下单、撤单、查询）
- 账户资金查询
- 持仓查询
- 历史数据查询

## 安装

```bash
pip install vnpy_tiger
```

## 使用方法

### 1. 在VeighNa中添加网关

```python
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy_tiger import TigerGateway

# 创建主引擎
event_engine = EventEngine()
main_engine = MainEngine(event_engine)

# 添加Tiger网关
main_engine.add_gateway(TigerGateway)
```

### 2. 连接配置

在VeighNa界面中配置以下参数：

- **tiger_id**: 老虎证券开发者ID
- **account**: 交易账户号
- **private_key_path**: 私钥文件路径
- **tiger_public_key_path**: 老虎证券公钥文件路径
- **environment**: 环境设置（sandbox/live）
- **language**: 语言设置（zh_CN/en_US）

### 3. 获取API密钥

1. 登录[老虎证券开放平台](https://quant.itiger.com/)
2. 创建应用获取Tiger ID
3. 下载私钥和公钥文件
4. 配置交易权限

## 支持的交易所

- NASDAQ: 纳斯达克
- NYSE: 纽约证券交易所  
- SEHK: 香港交易所
- SSE: 上海证券交易所
- SZSE: 深圳证券交易所

## 支持的订单类型

- 市价单 (MARKET)
- 限价单 (LIMIT)
- 止损单 (STOP)

## 注意事项

1. 使用前请确保已开通相应市场的交易权限
2. 沙盒环境用于测试，实盘环境用于真实交易
3. 请妥善保管API密钥，避免泄露
4. 建议先在沙盒环境测试后再切换到实盘

## 风险提示

- 量化交易存在风险，请谨慎操作
- 本软件仅供学习和研究使用
- 使用本软件进行实盘交易的风险由用户自行承担

## 技术支持

如有问题请提交Issue到：https://github.com/weijiaxing/vnpy_tiger/issues

## 许可证

MIT License