class KCandle_Type:
    minute, hour, day, month, year, MARK = range(6)


class KCandle:
    """ 
    define the basic candle stick class 
    There are five levels of candle sticks, from yearly ones to minites ones normally
    This class defines the basic element of the whole data structure, and the aim is to provide a tree 
    stuctural dataset constructed from security data input. (initially supporting stocks only)
    The data structure will be used for CHAN theory analyses
    """
    
    
    def __init__(self, iHigh=0, iLow=0, iVolume=0, iTimeStamp=None):
        self.h = iHigh
        self.l = iLow
        self.v = iVolume
        self.timestamp = iTimeStamp
        self.subCandle = [] # all sub level candles stored here
        self.candle_type = KCandle_Type.MARK # initial value
        
    def add_candle(self, iCandle):
        self.subCandle.append(iCandle)
    
    def copy_candle(self, iCandle):
        self.h = iCandle.iHigh
        self.l = iCandle.iLow
        self.v = iCandle.iVolume
        self.timestamp = iCandle.iTimeStamp
        self.subCandle = iCandle.subCandle # all sub level candles stored here
        
    def assign_candle_value(self, iHigh, iLow, iVolume, iTimeStamp):
        self.h = iHigh
        self.l = iLow
        self.v = iVolume
        self.timestamp = iTimeStamp
    
    def define_candle_type(self, iType):
        self.candle_type = iType
    
    