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
symbol = 'FTMUSDT'
interval = Client.KLINE_INTERVAL_1MINUTE
FIXED_USDT_AMOUNT = 20
LEVERAGE = 1
STOP_LOSS_PERCENTAGE = 0.015
quantity = 0

# 获取最新市场价格
def get_latest_market_price(symbol):
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        print(f"获取市价失败，错误信息为：{str(e)}")
        return 0

# 获取前一根K线的收盘价
def get_previous_close_price():
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=2)
    return float(klines[-2][4]) if len(klines) > 1 else 0

def get_ma(period, limit=0):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=period + limit)
    close_prices = np.array([float(kline[4]) for kline in klines[:-limit] or klines])
    return talib.SMA(close_prices, timeperiod=period)[-1]

# 获取技术指标：ADX, DI+, DI-, MACD
def get_technical_indicators():
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=50)
    high_prices = np.array([float(kline[2]) for kline in klines])
    low_prices = np.array([float(kline[3]) for kline in klines])
    close_prices = np.array([float(kline[4]) for kline in klines])

    adx = talib.ADX(high_prices, low_prices, close_prices, timeperiod=5)[-1]
    plus_di = talib.PLUS_DI(high_prices, low_prices, close_prices, timeperiod=5)[-1]
    minus_di = talib.MINUS_DI(high_prices, low_prices, close_prices, timeperiod=5)[-1]
    macd = talib.MACD(close_prices, fastperiod=12, slowperiod=26, signalperiod=9)[0][-1]
    return adx, plus_di, minus_di, macd

# 检查是否持仓
def has_position(symbol):
    try:
        account_info = client.futures_account()
        positions = account_info['positions']
        threshold = 1e-6
        for position in positions:
            if position['symbol'] == symbol and abs(float(position['positionAmt'])) > threshold:
                return {'positionSide': 'LONG' if float(position['positionAmt']) > 0 else 'SHORT', 'amount': abs(float(position['positionAmt']))}
        return None
    except Exception as e:
        print(f"检查持仓失败：{e}")
        return None

def close_position(symbol, position_side):
    try:
        close_side = Client.SIDE_SELL if position_side == 'LONG' else Client.SIDE_BUY
        order_type = Client.FUTURE_ORDER_TYPE_MARKET

        position_info = has_position(symbol)
        if position_info:
            quantity = abs(position_info['amount'])
            order = client.futures_create_order(
                symbol=symbol,
                side=close_side,
                type=order_type,
                positionSide=position_side,
                quantity=quantity,
            )
            print("----DONE----")
            return True
        else:
            print("没有持仓，无需平仓")
            return False
    except Exception as e:
        print(f"平仓失败：{e}")
        return False

# 获取交易对信息
def get_symbol_info(symbol):
    try:
        exchange_info = client.futures_exchange_info()
        for item in exchange_info['symbols']:
            if item['symbol'] == symbol:
                return item
    except Exception as e:
        print(f"获取交易对信息失败：{str(e)}")
        return None

# 更新账户余额信息
def get_account_balance():
    try:
        account_info = client.futures_account()
        balance = 0
        if 'assets' in account_info:
            for asset in account_info['assets']:
                if asset['asset'] == 'USDT':
                    balance = float(asset['walletBalance'])
        return balance
    except Exception as e:
        print(f"获取账户余额失败：{str(e)}")
        return 0

def get_price_change(symbol, interval, periods):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=max(periods) + 1)
    close_prices = np.array([float(kline[4]) for kline in klines])

    price_changes = {}
    for period in periods:
        if len(close_prices) > period:
            change = (close_prices[-1] - close_prices[-1-period]) / close_prices[-1-period]
            price_changes[period] = change
    return price_changes


# 调整精度
def adjust_precision(quantity, step_size):
    precision = int(round(-math.log(step_size, 10), 0))
    return round(quantity, precision)

# 取消所有订单
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

        balance = get_account_balance()
        if balance < FIXED_USDT_AMOUNT:
            print("账户余额不足，无法开仓")
            return False

        global quantity
        market_price = get_latest_market_price(symbol)
        # 计算购买数量
        quantity = FIXED_USDT_AMOUNT * LEVERAGE / market_price
        symbol_info = get_symbol_info(symbol)
        step_size = float(symbol_info['filters'][2]['stepSize'])
        quantity = adjust_precision(quantity, step_size)

        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=Client.FUTURE_ORDER_TYPE_MARKET,
            positionSide="SHORT" if side == Client.SIDE_SELL else "LONG",
            quantity=quantity,
            leverage=LEVERAGE,
        )
        print(f"{side}++++++++++++++++++++++++++++++++++++++++++++++++")

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

# 定义ATR计算函数
def get_atr(period=7):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=period+1)
    high_prices = np.array([float(kline[2]) for kline in klines])
    low_prices = np.array([float(kline[3]) for kline in klines])
    close_prices = np.array([float(kline[4]) for kline in klines])
    atr = talib.ATR(high_prices, low_prices, close_prices, timeperiod=period)[-1]
    return atr

# 定义ATR阈值
ATR_THRESHOLD = 0.005 # 示例值，您需要根据实际情况调整
# 主逻辑代码
while True:
    try:
        # 获取账户余额信息和市场价格
        balance = get_account_balance()
        latest_price = get_latest_market_price(symbol)
        print(f"FTM-------{balance:.2f}--------")

        # 获取前一根K线的收盘价和均线值
        prev_close_price = get_previous_close_price()
        prev_ma5 = get_ma(5, 1)  # 前一根K线的MA5
        prev_ma10 = get_ma(10, 1)  # 前一根K线的MA10
        prev_ma20 = get_ma(20, 1)  # 前一根K线的MA20
        prev_ma60 = get_ma(60, 1)  # 前一根K线的MA60

        # 获取当前MA值
        current_ma5 = get_ma(5)  # 当前MA5
        current_ma10 = get_ma(10)  # 当前MA10
        current_ma20 = get_ma(20)  # 当前MA20
        current_ma60 = get_ma(60)  # 当前MA60

        # 获取价格变化
        price_changes = get_price_change(symbol, interval, [5,10,20, 60])
        print(f"FTM----{price_changes:.4f}")
        
        # 获取ATR和技术指标
        atr = get_atr(5)
        adx, plus_di, minus_di, macd = get_technical_indicators()
        print(f"atr---:{atr:.4f},---adx---{adx:.4f},{plus_di:.4f},{minus_di:.4f}")

        # 检查买入条件
        if not has_position(symbol) and all([
            prev_close_price > prev_ma5, prev_close_price > prev_ma10, prev_close_price > prev_ma20, prev_close_price > prev_ma60, 
            latest_price > current_ma5, latest_price > current_ma10, latest_price > current_ma20, latest_price > current_ma60,
            current_ma5 > current_ma10, current_ma10 > current_ma20, atr > ATR_THRESHOLD, macd > 0,
            price_changes[5] > 0, price_changes[10] > 0, price_changes[20] > 0, price_changes[20] > 60,
            atr > ATR_THRESHOLD, adx > 20, plus_di > minus_di]):
            open_position(Client.SIDE_BUY)

        # 检查卖出条件
        elif not has_position(symbol) and all([
            prev_close_price < prev_ma5, prev_close_price < prev_ma10, prev_close_price < prev_ma20, prev_close_price < prev_ma60, 
            latest_price < current_ma5, latest_price < current_ma10, latest_price < current_ma20, latest_price < current_ma60,
            current_ma5 < current_ma10, current_ma10 < current_ma20, atr > ATR_THRESHOLD, macd < 0,
            price_changes[5] <  0, price_changes[10] <  0, price_changes[20] < 0, price_changes[20] < 60,
            atr > ATR_THRESHOLD, adx > 20, plus_di < minus_di]):
            open_position(Client.SIDE_SELL)

        # 检查平仓条件
        position_info = has_position(symbol)
        if position_info:
            position_side = position_info['positionSide']
            print(f"FTM-----{position_side}")

            # 对于多头持仓
            if position_side == 'LONG':
                if all([
                    latest_price < current_ma5, latest_price < current_ma10, 
                    prev_close_price < prev_ma5, prev_close_price < prev_ma10,
                    plus_di < minus_di]):
                    close_position(symbol, position_side)
                    cancel_all_orders(symbol)

            # 对于空头持仓
            elif position_side == 'SHORT':
                if all([
                    latest_price > current_ma5, latest_price > current_ma10, 
                    prev_close_price > prev_ma5, prev_close_price > prev_ma10,
                    plus_di > minus_di]):
                    close_position(symbol, position_side)
                    cancel_all_orders(symbol)

        # 设置循环延时，例如每5分钟检查一次
        time.sleep(20)

    except Exception as e:
        print("程序出现异常：", e)
        time.sleep(60)
        continue
    except KeyboardInterrupt:
        print("程序被中断")
        break
