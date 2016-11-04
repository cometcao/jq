'''
Created on 4 Oct 2016

@author: MetalInvest
'''

def isHammerHangman(high, low, open, close):
    body = abs(open - close)
    leg = min(open, close) - low
    return leg / body >= 2.0 and high/max(open, close) <= 1.08
    
def isEngulfing(df, bottom = True):
    open_0 = df['open'][-1]
    close_0 = df['close'][-1]
    open_1 = df['open'][-2]
    close_1 = df['close'][-2]
    body_0 = close_0 - open_0
    body_1 = close_1 - open_1
    if bottom: 
        return body_0 > 0 and body_1 < 0 and body_0 > abs(body_1)
    else:
        return body_0 < 0 and body_1 > 0 and abs(body_0) > body_1

def isDarkCloud():
    pass

def isPiercing():
    pass

def jap_candle_reversal(df, context):
    # we check strong trend reversal reversal_pattern
    index = 0.0
    # hammer & hangman
    if isHammerHangman(df['high'][-1], df['low'][-1], df['open'][-1], df['close'][-1]):
        index += g.reversal_index
    if isEngulfing(df):
        index += g.reversal_index
    return index