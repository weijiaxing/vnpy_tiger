"""
Unit tests for Tiger Gateway
"""

import unittest
from unittest.mock import Mock, patch
from vnpy.event import EventEngine
from vnpy_tiger import TigerGateway


class TestTigerGateway(unittest.TestCase):
    """Tiger Gateway测试用例"""

    def setUp(self):
        """测试初始化"""
        self.event_engine = EventEngine()
        self.gateway = TigerGateway(self.event_engine, "TIGER")

    def test_gateway_initialization(self):
        """测试网关初始化"""
        self.assertEqual(self.gateway.gateway_name, "TIGER")
        self.assertEqual(self.gateway.default_name, "TIGER")
        self.assertIsNotNone(self.gateway.default_setting)

    def test_default_setting(self):
        """测试默认配置"""
        setting = self.gateway.get_default_setting()
        required_keys = [
            "tiger_id", "account", "private_key_path", 
            "tiger_public_key_path", "environment", "language"
        ]
        for key in required_keys:
            self.assertIn(key, setting)

    @patch('vnpy_tiger.tiger_gateway.TradeClient')
    @patch('vnpy_tiger.tiger_gateway.QuoteClient')
    def test_connect_success(self, mock_quote_client, mock_trade_client):
        """测试连接成功"""
        # Mock配置
        setting = {
            "tiger_id": "test_id",
            "account": "test_account",
            "private_key_path": "/path/to/key.pem",
            "tiger_public_key_path": "/path/to/tiger_key.pem",
            "environment": "sandbox",
            "language": "zh_CN"
        }
        
        # Mock read_private_key
        with patch('vnpy_tiger.tiger_gateway.read_private_key') as mock_read_key:
            mock_read_key.return_value = "mock_private_key"
            
            # 执行连接
            self.gateway.connect(setting)
            
            # 验证客户端创建
            mock_trade_client.assert_called_once()
            mock_quote_client.assert_called_once()

    def test_connect_missing_credentials(self):
        """测试缺少凭证的连接"""
        setting = {
            "tiger_id": "",
            "account": "",
        }
        
        self.gateway.connect(setting)
        # 应该写入错误日志，但不会抛出异常

    def tearDown(self):
        """测试清理"""
        self.gateway.close()


if __name__ == '__main__':
    unittest.main()