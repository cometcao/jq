from xtquant.xttrader import XtQuantTrader
from xtquant.xttype import StockAccount
from xtquant import xtdata, xtconstant
import time

# ==================== 配置 ====================
path = r"D:\\gjzq\\QMT\\userdata_mini"          # 你的 userdata_mini 路径
account_id = "40188986"           # 替换为你的资金账号
stock_code = "000001.SZ"                 # 平安银行

# ==================== 连接 miniQMT ====================
session_id = int(time.time())
trader = XtQuantTrader(path, session_id)
trader.start()
time.sleep(3)

if trader.connect() != 0:
    print("连接失败")
    exit()

print("连接成功")

# ==================== 创建账户对象 ====================
account = StockAccount(account_id)

# ==================== 获取平安银行涨跌停价 ====================
print(f"\n获取 {stock_code} 的涨跌停价...")
try:
    detail = xtdata.get_instrument_detail(stock_code)
    if detail:
        high_limit = detail.get('UpStopPrice', 0.0)
        low_limit = detail.get('DownStopPrice', 0.0)
        print(f"涨停价: {high_limit:.2f}")
        print(f"跌停价: {low_limit:.2f}")
    else:
        print("未获取到合约信息")
except Exception as e:
    print(f"获取涨跌停价失败: {e}")

# ==================== 尝试卖出 100 股平安银行（废单） ====================
print(f"\n尝试卖出 {stock_code} 100股（废单测试）...")
try:
    # 使用跌停价作为卖出价格（实际废单不关心价格）
    price = low_limit if 'low_limit' in locals() and low_limit > 0 else 10.0
    # 下单：卖出 100 股，限价单
    order_id = trader.order_stock(
        account, 
        stock_code, 
        xtconstant.STOCK_SELL,   # 卖出方向
        100,                     # 数量
        xtconstant.FIX_PRICE,    # 限价单
        price,                   # 价格
        "test_sell_100"          # 备注
    )
    if order_id > 0:
        print(f"下单成功，订单号: {order_id}")
    else:
        print(f"下单失败，错误码: {order_id}")
except Exception as e:
    print(f"下单异常: {e}")

# ==================== 关闭连接 ====================
trader.stop()
print("\n测试结束")