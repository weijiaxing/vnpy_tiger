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

- **tiger_id**: 老虎证券开发者ID（必需）
- **account**: 交易账户号（必需）
- **private_key** 或 **private_key_path**: 私钥配置（二选一）
  - `private_key`: 直接提供私钥内容字符串（推荐，更安全）
  - `private_key_path`: 提供私钥文件路径
- **tiger_public_key_path**: 老虎证券公钥文件路径（可选）
- **environment**: 环境设置（sandbox/live，默认sandbox）
- **language**: 语言设置（zh_CN/en_US，默认zh_CN）
- **max_contracts**: 最大加载合约数量（默认100，避免加载过多导致卡顿）
- **use_preset_contracts**: 是否仅使用预设合约（true/false，默认false）

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

## 常见问题

### 1. "cannot import name 'runtime_version'" 错误

这是 protobuf 版本问题。Tiger官方SDK使用Protobuf 5.x生成，需要安装对应版本。

**快速修复方法：**

```bash
# 方法一：运行快速修复脚本
chmod +x quick_fix.sh
./quick_fix.sh

# 方法二：手动修复
pip uninstall protobuf tigeropen -y
pip install protobuf>=5.0.0
pip install tigeropen

# 方法三：使用诊断工具
python fix_dependencies.py
```

**注意**：如果你的其他项目需要旧版protobuf，建议使用虚拟环境隔离。

### 2. 推送服务不可用

如果看到"推送服务不可用"的提示，不影响基本交易功能，只是无法接收实时推送。

### 3. 合约加载过多导致卡顿

调整 `max_contracts` 参数来限制加载的合约数量（默认100）。

## 注意事项

1. 使用前请确保已开通相应市场的交易权限
2. 沙盒环境用于测试，实盘环境用于真实交易
3. 请妥善保管API密钥，避免泄露
4. 建议先在沙盒环境测试后再切换到实盘

## 风险提示

- 量化交易存在风险，请谨慎操作
- 本软件仅供学习和研究使用
- 使用本软件进行实盘交易的风险由用户自行承担

## 更新日志

### v1.0.2 (2025-08-12)
- ✅ **修复合约查询功能**：实现使用Tiger API的`get_symbol_names()`动态获取股票列表
- ✅ **改进推送连接错误处理**：提供更详细的错误信息和解决建议
- ✅ **新增配置选项**：
  - `max_contracts`: 控制加载合约数量，避免加载过多导致系统卡顿
  - `use_preset_contracts`: 允许用户选择仅使用预设合约
- ✅ **修复状态映射错误**：VeighNa没有CANCELLING状态，改为使用CANCELLED
- ✅ **优化日志输出**：提供更清晰的诊断信息

### v1.0.1 (2025-08-12)
- ✅ 修复实时行情推送功能，正确生成TickData对象
- ✅ 修复成交数据生成，实现TradeData推送
- ✅ 修复配置结构不一致问题，支持私钥字符串和文件路径两种方式
- ✅ 修复行情接口测试时缺少必需参数的问题
- ✅ 改进代码注释和文档，增强代码可维护性
- ✅ 增强符号转换函数的健壮性

### v1.0.0
- 初始版本发布
- 支持美股、港股、A股交易
- 实现基本的交易和行情功能

## 技术支持

如有问题请提交Issue到：https://github.com/weijiaxing/vnpy_tiger/issues

## 许可证

MIT License