'''
Created on 24 Oct 2017

@author: MetalInvest
'''

import enum

class TaType(enum.Enum):
    MACD = 0,
    RSI = 1,
    BOLL = 2,
    MA = 3, 
    MACD_STATUS = 4,
    TRIX = 5,
    BOLL_UPPER = 6,
    TRIX_STATUS = 7,
    TRIX_PURE = 8,
    MACD_ZERO = 9,
    MACD_CROSS = 10,
    KDJ_CROSS = 11,
    BOLL_MACD = 12

    def __le__(self, b):
        return self.value <= b.value
