import time
from binance.client import Client
import talib
import numpy as np
from binance.exceptions import BinanceAPIException
# 填写自己的币安API Key和Secret
api_key = 'GjHUW3DZFizTt7rfuoI58xebWaMtDOMxjWJjjG34f8wiJRdUjE7l24b8L046StvI'
api_secret = '7JJ079zKEEeO6wZnSHhxDRkx81CG0AFvl7450PixmSl9UP0F3yoMlupCRJGtz5KK'
# 初始化币安客户端
client = Client(api_key=api_key, api_secret=api_secret)
# 交易对和K线周期
symbol = 'FTMUSDT'
interval = Client.KLINE_INTERVAL_5MINUTE
QUANTITY = 2000
LEVERAGE = 50
TIME_GAP = 5
STOP_LOSS_PERCENTAGE = 0.5
# 获取前一根K线数据
def get_previous_close_price(symbol):
    klines = client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_5MINUTE, limit=2)
    if len(klines) >= 2:
        previous_kline_close_price = float(klines[-2][4])
        return previous_kline_close_price
    else:
        return 0
def get_previous_ma(timeperiod):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=timeperiod*3)
    close_prices = np.array([float(kline[4]) for kline in klines])
    ma = talib.SMA(close_prices, timeperiod=timeperiod)[-2]
    return ma
def get_previous_ma7_and_ma28():
    ma7 = get_previous_ma(timeperiod=7)
    ma28 = get_previous_ma(timeperiod=28)
    return ma7, ma28
# 检查是否持仓
def has_position(symbol):
    positions = client.futures_position_information()
    threshold = 1e-6
    for position in positions:
        if position['symbol'] == symbol:
            position_amt = float(position['positionAmt'])
            if abs(position_amt) > threshold:
                return {'position': position, 'positionAmt': position_amt}
    return False

def close_position(symbol, position_side):
    try:
        close_side = Client.SIDE_SELL if position_side == 'LONG' else Client.SIDE_BUY
        order_type = Client.FUTURE_ORDER_TYPE_MARKET

        positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            if position['positionSide'] == position_side and float(position['positionAmt']) != 0:
                order = client.futures_create_order(
                    symbol=symbol,
                    side=close_side,
                    type=order_type,
                    positionSide=position_side,
                    quantity=abs(float(position['positionAmt'])),
                )
                print(f"平仓成功，订单ID：{order['orderId']}")
                return True
        print("没有持仓，无需平仓")
        return False
    except Exception as e:
        print(f"平仓失败：{e}")
        return False

# 开仓函数
def open_position(side):
    try:
        position = has_position(symbol)
        if position:
            print("已开仓")
            return False

        balances = client.futures_account_balance()
        balance = 0
        for b in balances:
            if b['asset'] == 'USDT':
                balance = float(b['balance'])
        if balance < 20:
            print("账户余额不足，无法开仓")
            return False

        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=Client.FUTURE_ORDER_TYPE_MARKET,
            positionSide="SHORT" if side == Client.SIDE_SELL else "LONG",
            quantity=QUANTITY,
            leverage=LEVERAGE,
        )
        print(f"做{side}开仓成功")
        print(f"订单参数： {order}")

        order_id = order['orderId']
        order_info = client.futures_get_order(symbol=symbol, orderId=order_id)
        avg_fill_price = float(order_info['avgPrice'])
        stop_loss_percentage = 1 - STOP_LOSS_PERCENTAGE if side == Client.SIDE_BUY else 1 + STOP_LOSS_PERCENTAGE
        stop_loss_price = round(avg_fill_price * stop_loss_percentage, 2)

        try:
            stop_order = client.futures_create_order(
                symbol=symbol,
                side=Client.SIDE_SELL if side == Client.SIDE_BUY else Client.SIDE_BUY,
                type=Client.FUTURE_ORDER_TYPE_STOP_MARKET,
                positionSide="LONG" if side == Client.SIDE_BUY else "SHORT",
                stopPrice=stop_loss_price,
                quantity=QUANTITY,
                timeInForce="GTC",
            )
            print(f"{side}开仓成功，止损价格为{stop_loss_price}")
            return {'order_id': order_id, 'stop_loss_price': stop_loss_price}
        except BinanceAPIException as e:
            print(f"创建止损单失败：{e}")
            return False
    except Exception as e:
        print(f"开仓失败：{e}")
        return False




# 主逻辑代码
last_print_time = 0  # 上次打印信息的时间
while True:
    try:
        # 判断距离上次打印信息的时间是否超过5秒钟，若未超过，则继续等待
        if time.time() - last_print_time < TIME_GAP:
            time.sleep(1)
            continue
        # 获取账户余额信息
        balances = client.futures_account_balance()
        balance = 0  # 初始化USDT余额为0
        for b in balances:
            if b['asset'] == 'USDT':
                balance = float(b['balance'])
        # 打印账户余额信息
        print(f"当前账户USDT余额为：{balance}")
        # 获取前一根K线的收盘价和MA7、MA28的值
        ma7, ma28 = get_previous_ma7_and_ma28()
        prev_close_price = get_previous_close_price(symbol)
        print(f"收盘价: {prev_close_price}, MA7: {ma7}, MA28: {ma28}")
        if prev_close_price and prev_close_price > max(ma7, ma28):
            # 当前趋势为上涨，开多头仓位
            open_position(Client.SIDE_BUY)
            last_print_time = time.time()
            print("多头趋势")
        elif prev_close_price and prev_close_price < min(ma7, ma28):
            # 当前趋势为下跌，开空头仓位
            open_position(Client.SIDE_SELL)
            last_print_time = time.time()
            print("空头趋势")
        position = has_position(symbol)
        if position:
            position_side = position['position']['positionSide']
            print(f"持仓方向：{position_side}")
            print(f"收盘价：{prev_close_price}, MA7: {ma7}, MA28: {ma28}")

            if (position_side == 'LONG' and prev_close_price < ma7) or (
                    position_side == 'SHORT' and prev_close_price > ma7):
                close_position(symbol, position_side)
                print(f"平仓成功，价格：{prev_close_price}")
            else:
                print("暂时不满足平仓条件")
        time.sleep(TIME_GAP)  # 每隔5秒执行一次
    except Exception as e:
        print("程序出现异常：", e)
        time.sleep(TIME_GAP)
        continue
    except KeyboardInterrupt:
        print("程序被中断")
        break








