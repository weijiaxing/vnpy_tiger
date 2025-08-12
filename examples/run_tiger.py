"""
Tiger Securities Gateway Example
"""

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp

from vnpy_tiger import TigerGateway


def main():
    """启动VeighNa Trader with Tiger Gateway"""
    qapp = create_qapp()

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    
    # 添加Tiger网关
    main_engine.add_gateway(TigerGateway)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":
    # Tiger Securities连接配置示例
    tiger_setting = {
        "tiger_id": "your_tiger_id",
        "account": "your_account",
        "private_key_path": "/path/to/your/private_key.pem",
        "tiger_public_key_path": "/path/to/tiger_public_key.pem", 
        "environment": "sandbox",  # sandbox 或 live
        "language": "zh_CN",
    }
    
    print("Tiger Securities Gateway配置示例:")
    print("请在VeighNa界面中配置以下参数:")
    for key, value in tiger_setting.items():
        print(f"  {key}: {value}")
    print("\n启动VeighNa Trader...")
    
    main()