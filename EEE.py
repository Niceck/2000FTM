import time
import math
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
symbol = 'ETHUSDT'
interval = Client.KLINE_INTERVAL_15MINUTE
FIXED_USDT_AMOUNT = 100
LEVERAGE = 50
TIME_GAP = 900
STOP_LOSS_PERCENTAGE = 0.006
quantity = 0
def get_latest_market_price(symbol):
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        print(f"获取市价失败，错误信息为：{str(e)}")
        return 0
def get_latest_MA(timeperiod):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=timeperiod+1)
    close_prices = np.array([float(kline[4]) for kline in klines])
    MA = talib.SMA(close_prices, timeperiod=timeperiod)[-1]
    return MA
def get_latest_MA7_and_MA14_and_MA28():
    MA7 = get_latest_MA(timeperiod=7)
    MA14 = get_latest_MA(timeperiod=14)
    MA28 = get_latest_MA(timeperiod=28)
    return MA7, MA14, MA28
def get_previous_close_price(symbol):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=2)
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
def get_previous_ma7_ma14_and_ma28():
    ma7 = get_previous_ma(timeperiod=7)
    ma14 = get_previous_ma(timeperiod=14)
    ma28 = get_previous_ma(timeperiod=28)
    return ma7, ma14, ma28
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

def close_position(symbol, position_side, prev_close_price, deviation):
    try:
        close_side = Client.SIDE_SELL if position_side == 'LONG' else Client.SIDE_BUY
        order_type = Client.FUTURE_ORDER_TYPE_MARKET

        positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            if position['positionSide'] == position_side and float(position['positionAmt']) != 0:
                quantity = abs(float(position['positionAmt']))  # 计算quantity
                order = client.futures_create_order(
                    symbol=symbol,
                    side=close_side,
                    type=order_type,
                    positionSide=position_side,
                    quantity=quantity,
                )
                print(f"平仓成功：{prev_close_price},乖离率: {deviation:.2f},--------------------------------------------")
                return True
        print("没有持仓，无需平仓")
        return False
    except Exception as e:
        print(f"平仓失败：{e}")



def get_symbol_info(symbol):
    try:
        exchange_info = client.futures_exchange_info()
        for item in exchange_info['symbols']:
            if item['symbol'] == symbol:
                return item
    except Exception as e:
        print(f"获取交易对信息失败：{str(e)}")
        return None

symbol_info = get_symbol_info(symbol)
step_size = float(symbol_info['filters'][2]['stepSize'])
def adjust_precision(quantity, step_size):
    precision = int(round(-math.log(step_size, 10), 0))
    return round(quantity, precision)

def cancel_all_orders(symbol):
    try:
        orders = client.futures_get_open_orders(symbol=symbol)
        for order in orders:
            client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
            print(f"已取消订单，订单ID：{order['orderId']}")
        return True
    except Exception as e:
        print(f"取消委托单失败：{e}")
        return False


# 开仓函数
def open_position(side):
    try:
        position = has_position(symbol)
        if position:
            return False

        balances = client.futures_account_balance()
        balance = 0
        for b in balances:
            if b['asset'] == 'USDT':
                balance = float(b['balance'])
        if balance < FIXED_USDT_AMOUNT:
            print("账户余额不足，无法开仓")
            return False
        global quantity  # 声明全局变量
        market_price = get_latest_market_price(symbol)
        # 计算购买数量
        quantity = FIXED_USDT_AMOUNT * LEVERAGE / market_price
        quantity = adjust_precision(quantity, step_size)

        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=Client.FUTURE_ORDER_TYPE_MARKET,
            positionSide="SHORT" if side == Client.SIDE_SELL else "LONG",
            quantity=quantity,
            leverage=LEVERAGE,
        )
        print(f"做{side}开仓成功，乖离率: {deviation:.2f}，++++++++++++++++++++++++++++++++++++++++++++++++")

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
                quantity=quantity,
                timeInForce="GTC",
            )
            print(f"止损价格为{stop_loss_price}")
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
        print(f"当前账户USDT余额为：{balance:.2f}")
        # 获取前一根K线的收盘价和MA7、MA28的值
        latest_market_price = get_latest_market_price(symbol)
        MA7, MA14, MA28 = get_latest_MA7_and_MA14_and_MA28()
        ma7, ma14, ma28 = get_previous_ma7_ma14_and_ma28()
        prev_close_price = get_previous_close_price(symbol)
        deviation = (latest_market_price - MA7) / MA7
        deviation = deviation * 100.0
        print(f"市价: {latest_market_price:.4f}, 乖离率: {deviation:.2f}")
        if latest_market_price > max(MA7,MA14,MA28) and deviation <= 0.4:
            # 当前趋势为上涨，开多头仓位
            open_position(Client.SIDE_BUY)
            last_print_time = time.time()
            print(f"多头趋势")
        elif latest_market_price < min(MA7,MA14,MA28) and deviation >= -0.4:
            # 当前趋势为下跌，开空头仓位
            open_position(Client.SIDE_SELL)
            last_print_time = time.time()
            print(f"空头趋势")
        position = has_position(symbol)
        if position:
            position_side = position['position']['positionSide']
            print(f"持仓方向：{position_side}")
            if ((position_side == 'LONG' and (latest_market_price < MA7 or deviation >= 1 or deviation <= -0.1)) or
                    (position_side == 'SHORT' and (latest_market_price > MA7 or deviation <= -1 or deviation >= 0.1))):
                close_position(symbol, position_side, prev_close_price, deviation)
                cancel_all_orders(symbol)

        time.sleep(TIME_GAP)  # 每隔5秒执行一次
    except Exception as e:
        print("程序出现异常：", e)
        time.sleep(TIME_GAP)
        continue
    except KeyboardInterrupt:
        print("程序被中断")
        break
