from biaoLiStatus import * 
from kBarProcessor import *
from centralRegion import *

import numpy as np
import pandas as pd
from pytz.reference import Central


class Equilibrium():
    '''
    This class use ZouShi analytic results to check BeiChi
    '''
    
    def __init__(self, df_all, analytic_result, isdebug=False, isDescription=True):
        self.original_df = df_all
        self.analytic_result = analytic_result
        self.isdebug = isdebug
        self.isDescription = isDescription
        self.isQvShi = False
        pass
    
    def find_most_recent_zoushi(self):
        '''
        Make sure we return the most recent Zhong Shu and the Zou Shi Lei Xing Entering it.
        The Zou Shi Lei Xing Exiting it will be reworked on the original df
        '''
        if type(self.analytic_result[-1]) is ZhongShu:
            filled_zslx = self.analytic_result[-1].take_last_xd_as_zslx()
            return self.analytic_result[-2], self.analytic_result[-1], filled_zslx
        elif type(self.analytic_result[-1]) is ZouShiLeiXing:
            return self.analytic_result[-3], self.analytic_result[-2], self.analytic_result[-1]
        else:
            print("Invalid Zou Shi type")
            return None, None, None
    
    def define_equilibrium(self):
        # check if current status beichi or panzhengbeichi
        self.check_equilibrium_status()
        
        a, B, c = self.find_most_recent_zoushi()
        
        return self.check_exhaustion(a, B, c)
        
    def check_exhaustion(self, zslx_a, zs_B, zslx_c):
        zslx_slope = zslx_a.work_out_slope()
        
        latest_slope = zslx_c.work_out_slope()

        if np.sign(latest_slope) == 0 or np.sign(zslx_slope) == 0:
            if self.isdebug:
                print("Invalid slope {0}, {1}".format(zslx_slope, latest_slope))
            return False
        
        if np.sign(latest_slope) == np.sign(zslx_slop) and abs(latest_slope) < abs(zslx_slope):
            if self.isdebug:
                print("exhaustion found by reduced slope: {0} {1}".format(zslx_slope, latest_slope))
            return True

        if self.isQvShi: # if QV SHI => at least two Zhong Shu, We could also use macd for help
            zslx_macd = zslx_a.get_macd_acc()
            latest_macd = zslx_c.get_macd_acc()
            return abs(zslx_macd) > abs(latest_macd)
        return False
         
    def check_equilibrium_status(self):
        recent_zoushi = self.analytic_result[-4:]
        recent_zhongshu = []
        for zs in recent_zoushi:
            if type(zs) is ZhongShu:
                recent_zhongshu.append(zs)
                
        if len(recent_zhongshu) >= 2 and\
            (recent_zhongshu[-2].direction == recent_zhongshu[-1].direction or recent_zhongshu[-2].is_complex_type()):
            if recent_zhongshu[-2].get_level().value >= recent_zhongshu[-1].get_level().value:
                [l1, u1] = recent_zhongshu[-2].get_amplitude_region()
                [l2, u2] = recent_zhongshu[-1].get_amplitude_region()
                if l1 > u2 or l2 > u1: # two Zhong Shu without intersection
                    if self.isDescription or self.isdebug:
                        print("current Zou Shi is QV SHI")
                    self.isQvShi = True
        else:
            self.isQvShi = False
            
        return self.isQvShi
    
    
class NestedInterval():            
    '''
    This class utilize BEI CHI and apply them to multiple nested levels, 
    existing level goes:
    current_level -> XD -> BI
    '''
    def __init__(self, df_xd_bi, isdebug=False, isDescription=True):
        self.df_xd_bi = df_xd_bi
        self.isdebug = isdebug
        self.isDescription = isDescription
    
    def analyze_zoushi(self, use_xd):
        crp = CentralRegionProcess(self.df_xd_bi, isdebug=self.isdebug, use_xd=use_xd) # XD
        analytics = crp.define_central_region()
        
        eq = Equilibrium(self.df_xd_bi, analytics,self.isdebug)
        return eq.define_equilibrium(), analytics[-1].direction
    
    def is_trade_point(self, direction):
        '''
        use direction param to check long/short point
        '''
        if self.isDescription or self.isdebug:
            print("looking for {0} point".format("long" if direction == TopBotType.top2bot else "short"))
        # XD
        xd_exhausted, xd_direction = self.analyze_zoushi(use_xd=True)
        if self.isDescription or self.isdebug:
            print("Xian Duan {0} {1}".format(xd_direction, "exhausted" if xd_exhausted else "continues"))
        
        # BI
        bi_exhausted, bi_direction = self.analyze_zoushi(use_xd=False)
        if self.isDescription or self.isdebug:
            print("Fen Bi {0} {1}".format(bi_direction, "exhausted" if bi_exhausted else "continues"))
        
        return xd_direction == bi_direction == direction and xd_exhausted and bi_exhausted


        
                