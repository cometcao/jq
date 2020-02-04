try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *

from biaoLiStatus import * 
from kBarProcessor import *
from centralRegion import *

import numpy as np
import pandas as pd

def check_chan_type(stock, end_time, count, period, direction, chan_type, isdebug=False, is_anal=True):
    if is_anal:
        stock_high = get_price(stock, count=count, end_date=end_time, frequency=period,fields= ['open',  'high', 'low','close'], skip_paused=True)
    else:
        stock_high = attribute_history(stock, count=count, unit=period,fields= ['open',  'high', 'low','close'], skip_paused=True)
    kb_high = KBarProcessor(stock_high, isdebug=isdebug)
    xd_df_high = kb_high.getIntegradedXD()
    crp_high = CentralRegionProcess(xd_df_high, isdebug=isdebug, use_xd=True)
    anal_result_high_zoushi = crp_high.define_central_region()
    if anal_result_high_zoushi is not None:
        eq = Equilibrium(xd_df_high, anal_result_high_zoushi.zslx_result, isdebug=isdebug, isDescription=True)
        chan_types = eq.check_chan_type(check_end_tb=False)
        for chan_t, chan_d,_ in chan_types:
            if chan_t == chan_type and chan_d == direction:
                return True
    return False

def check_chan_exhaustion(stock, end_time, count, period, direction, isdebug=False, is_anal=True):
    if is_anal:
        stock_df = get_price(stock, count=count, end_date=end_time, frequency=period,fields= ['open',  'high', 'low','close'],skip_paused=True)
    else:
        stock_df = attribute_history(stock, count=count, unit=period, fields= ['open',  'high', 'low','close'],skip_paused=True)
    kb = KBarProcessor(stock_df, isdebug=isdebug)
    xd_df = kb.getIntegradedXD()
    
    crp = CentralRegionProcess(xd_df, isdebug=isdebug, use_xd=True)
    anal_result_zoushi = crp.define_central_region()
    
    if anal_result_zoushi is not None:
        eq = Equilibrium(xd_df, anal_result_zoushi.zslx_result, isdebug=isdebug, isDescription=True)
        return eq.define_equilibrium(direction)
    else:
        return False

def check_chan_by_type_exhaustion(stock, end_time, periods, count, direction, chan_type, isdebug=False, is_anal=False):
    ni = NestedInterval(stock, 
                        end_dt=end_time, 
                        periods=periods, 
                        count=count, 
                        isdebug=isdebug, 
                        isDescription=True,
                        isAnal=is_anal)
    
    return ni.analyze_zoushi(direction, chan_type)

def check_chan_indepth(stock, end_time, period, count, direction, isdebug=False, is_anal=False):
    ni = NestedInterval(stock, 
                        end_dt=end_time, 
                        periods=[period], 
                        count=count, 
                        isdebug=isdebug, 
                        isDescription=True,
                        isAnal=is_anal)
    return ni.indepth_analyze_zoushi(direction)

def check_stock_full(stock, end_time, periods=['5m', '1m'], count=2000, direction=TopBotType.top2bot, isdebug=False, is_anal=False):
    print("working on stock: {0}".format(stock))
    ni = NestedInterval(stock, 
                        end_dt=end_time, 
                        periods=periods, 
                        count=count,
                        isdebug=isdebug, 
                        isDescription=True,
                        isAnal=is_anal)
    
    top_pe = periods[0]
    exhausted, chan_types, splitTime = ni.full_check_zoushi(top_pe, 
                                                     direction, 
                                                     check_end_tb=False, 
                                                     check_tb_structure=False, 
                                                     check_xd_exhaustion=False, 
                                                     split_time=None)
    stock_profile = [chan_types[0]]
    if exhausted:
        chan_t, chan_d, chan_p = chan_types[0]
        i = 1
        while i < len(periods):
            sub_exhausted, sub_chan_types, sub_splitTime = ni.full_check_zoushi(periods[i], 
                                                                                 direction, 
                                                                                 check_end_tb=True, 
                                                                                 check_tb_structure=True, 
                                                                                 check_xd_exhaustion=True, 
                                                                                 split_time=None)
            stock_profile.append(sub_chan_types[0])
            if not sub_exhausted:
                return False, stock_profile
            splitTime = sub_splitTime
            i = i + 1
        return True, stock_profile
    else:
        return False, stock_profile

class CentralRegionProcess(object):
    '''
    This lib takes XD data, and the dataframe must contain chan_price, new_index, xd_tb, macd columns
    '''
    def __init__(self, kDf, high_df=None, isdebug=False, use_xd=True):    
        self.original_xd_df = kDf
        self.high_level_df = high_df
        self.use_xd = use_xd
        self.zoushi = None
        self.isdebug = isdebug
        
    def find_initial_direction_highlevel(self):
        # higher level df data, find nearest top or bot
        # use 30m or 1d
        max_price_idx = self.high_level_df['close'].idxmax()
        min_price_idx = self.high_level_df['close'].idxmin()
        initial_idx = max(max_price_idx, min_price_idx)
        initial_direction = TopBotType.top2bot if max_price_idx > min_price_idx else TopBotType.bot2top
        if self.isdebug:
            print("initial direction: {0}, start idx {1}".format(initial_direction, initial_idx))
        return initial_idx, initial_direction  
    

    def work_out_direction(self, first, second, third):
        assert first.tb == third.tb, "Invalid tb information for direction"
        result_direction = TopBotType.noTopBot
        if first.tb == TopBotType.top and second.tb == TopBotType.bot:
            result_direction = TopBotType.bot2top if third.chan_price > first.chan_price else TopBotType.top2bot
        elif first.tb == TopBotType.bot and second.tb == TopBotType.top:
            result_direction = TopBotType.bot2top if third.chan_price > first.chan_price else TopBotType.top2bot
        else:
            print("Invalid tb data!!")
            
        return result_direction
    
    
    def find_initial_direction(self, working_df): 
        i = 0
        if working_df.shape[0] < 3:
            if self.isdebug:
                print("not enough data for checking initial direction")
            return 0, TopBotType.noTopBot
        
        first = working_df.iloc[i]
        second = working_df.iloc[i+1]
        third = working_df.iloc[i+2]
        
#         if ZouShiLeiXing.is_valid_central_region(TopBotType.bot2top, first, second, third, forth):
#             initial_direction = TopBotType.bot2top
#             initial_idx = working_df.index[i]
#         elif ZouShiLeiXing.is_valid_central_region(TopBotType.top2bot, first, second, third, forth):
#             initial_direction = TopBotType.bot2top
#             initial_idx = working_df.index[i]
#         else: # case of ZSLX
        initial_direction = self.work_out_direction(first, second, third)
        initial_idx = working_df.index[i]
        
        if self.isdebug:
            print("initial direction: {0}, start idx {1}".format(initial_direction, initial_idx))
        return initial_idx, initial_direction  
        
    
    def find_central_region(self, initial_idx, initial_direction, working_df):
        working_df = working_df.loc[initial_idx:,:]
        
        zoushi = ZouShi([XianDuan_Node(working_df.iloc[i]) for i in range(working_df.shape[0])], self.original_xd_df,isdebug=self.isdebug) if self.use_xd else ZouShi([BI_Node(working_df.iloc[i]) for i in range(working_df.shape[0])], self.original_xd_df, isdebug=self.isdebug)
        zoushi.analyze(initial_direction)

        return zoushi
    
    def define_central_region(self):
        '''
        We probably need fully integrated stock df with xd_tb
        '''
        if self.original_xd_df.empty:
            if self.isdebug:
                print("empty data, return define_central_region")            
            return None
        working_df = self.original_xd_df        
        
        working_df = self.prepare_df_data(working_df)
        
        init_idx, init_d = self.find_initial_direction(working_df)
        
        if init_d == TopBotType.noTopBot: # not enough data, we don't do anything
            if self.isdebug:
                print("not enough data, return define_central_region")
            return None
        
        self.zoushi = self.find_central_region(init_idx, init_d, working_df)
            
        return self.zoushi
        
    def convert_to_graph_data(self):
        '''
        We are assuming the Zou Shi is disassembled properly with data in timely order
        '''
        x_axis = []
        y_axis = []
        for zs in self.zoushi.zslx_result:
            if type(zs) is ZhongShu:
                print(zs)
                x_axis = x_axis + zs.get_core_time_region()
                y_axis = y_axis + zs.get_core_region()
            else:
                continue
        
        return x_axis, y_axis
        
        
    def prepare_df_data(self, working_df):        
        _, _, working_df.loc[:,'macd'] = talib.MACD(working_df['close'].values)

        tb_name = 'xd_tb' if self.use_xd else 'tb'
        working_df = self.prepare_macd(working_df, tb_name)

        working_df = working_df[(working_df[tb_name]==TopBotType.top) | (working_df[tb_name]==TopBotType.bot)]
        
        if self.isdebug:
            print("working_df: {0}".format(working_df[['chan_price', tb_name, 'new_index','macd_acc_'+tb_name]]))
        return working_df
    
    def prepare_macd(self, working_df, tb_col):
        working_df['tb_pivot'] = working_df.apply(lambda row: 0 if pd.isnull(row[tb_col]) else 1, axis=1)
        groups = working_df['tb_pivot'][::-1].cumsum()[::-1]
        working_df['tb_pivot_acc'] = groups
        
        df_macd_acc = working_df.groupby(groups)['macd'].agg([('macd_acc_negative' , lambda x : x[x < 0].sum()) , ('macd_acc_positive' , lambda x : x[x > 0].sum())])
        working_df = pd.merge(working_df, df_macd_acc, left_on='tb_pivot_acc', right_index=True)
        working_df['macd_acc_'+tb_col] = working_df.apply(lambda row: 0 if pd.isnull(row[tb_col]) else row['macd_acc_negative'] if row[tb_col] == TopBotType.bot else row['macd_acc_positive'] if row[tb_col] == TopBotType.top else 0, axis=1)
        
        working_df.drop(['tb_pivot', 'tb_pivot_acc', 'macd_acc_negative', 'macd_acc_positive'], axis=1, inplace=True)
        
        return working_df

def take_start_price(elem):
    if len(elem.zoushi_nodes) > 0:
        return elem.zoushi_nodes[-1].chan_price
    else:
        return 0

class Equilibrium():
    '''
    This class use ZouShi analytic results to check BeiChi
    '''
    
    def __init__(self, df_all, zslx_result, isdebug=False, isDescription=True):
        self.original_df = df_all
        self.analytic_result = zslx_result
        self.isdebug = isdebug
        self.isDescription = isDescription
        self.isQvShi = False
        self.check_zoushi_status()
        pass
    
    def find_most_recent_zoushi(self, direction):
        '''
        Make sure we find the appropriate two XD for comparison.
        A. in case of QVSHI
        B. in case of no QVSHI
            1. compare the entering zhongshu XD/split XD with last XD of the zhongshu
            2. compare entering XD with exit XD for the group of complicated zhongshu
            3. compare two zslx entering and exiting zhongshu (can be opposite direction)
        '''
        if self.isQvShi:
            if type(self.analytic_result[-1]) is ZhongShu and self.analytic_result[-1].is_complex_type():  
                zs = self.analytic_result[-1]
                first_zslx = self.analytic_result[-2]
                last_xd = zs.take_last_xd_as_zslx()
                return (first_zslx, self.analytic_result[-1], last_xd) if last_xd.direction == direction else (None, None, None)
            elif type(self.analytic_result[-1]) is ZouShiLeiXing:
                return (self.analytic_result[-3], self.analytic_result[-2], self.analytic_result[-1]) if self.analytic_result[-1].direction == direction else (None, None, None)
            else:
                print("Invalid Zou Shi type")
                return None, None, None
        else:
            if type(self.analytic_result[-1]) is ZhongShu and\
                self.analytic_result[-1].is_complex_type():
                zs = self.analytic_result[-1]
                last_xd = zs.take_last_xd_as_zslx()
                if last_xd.direction != direction:
                    return None, None, None
                
                if len(self.analytic_result) >= 3 and\
                    type(self.analytic_result[-2]) is ZouShiLeiXing and\
                    type(self.analytic_result[-1]) is ZhongShu and\
                    type(self.analytic_result[-3]) is ZhongShu and\
                    self.two_zslx_interact_original(self.analytic_result[-1], self.analytic_result[-3]):
                    ## zhong shu combination
                    i = -3
                    marked = False
                    while -(i-2) <= len(self.analytic_result):
                        if not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i]) or\
                            (not self.analytic_result[i-2].is_complex_type() and self.analytic_result[i-2].direction != self.analytic_result[i].direction):
                            first_xd = self.analytic_result[i-1]
                            zs = self.analytic_result[i:-1]
                            marked = True
                            break
                        i = i - 2
                    if not marked or -(i-2) > len(self.analytic_result):
                        all_zs = [zs for zs in self.analytic_result if type(zs) is ZhongShu]
                        all_first_xd = [zs.take_first_xd_as_zslx(direction) for zs in all_zs]
                        first_xd = sorted(all_first_xd, key=take_start_price, reverse=direction==TopBotType.top2bot)[0]
                        
                elif len(self.analytic_result) < 2 or self.analytic_result[-2].direction != last_xd.direction:
                    first_xd = zs.take_first_xd_as_zslx(direction)
                else:
                    first_xd = self.analytic_result[-2]
                return first_xd, zs, last_xd

            elif type(self.analytic_result[-1]) is ZouShiLeiXing:
                last_xd = self.analytic_result[-1]
                zs = self.analytic_result[-2]
                if last_xd.direction != direction:
                    return None, None, None
                
                if len(self.analytic_result) >= 4 and\
                    type(self.analytic_result[-2]) is ZhongShu and\
                    type(self.analytic_result[-4]) is ZhongShu and\
                    self.two_zslx_interact_original(self.analytic_result[-4], self.analytic_result[-2]):
                    ## zhong shu combination
                    i = -4
                    marked = False
                    while -(i-2) <= len(self.analytic_result):
                        if not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i]) or\
                            (not self.analytic_result[i-2].is_complex_type() and self.analytic_result[i-2].direction != self.analytic_result[i].direction):
                            first_xd = self.analytic_result[i-1]
                            zs = self.analytic_result[i:-1]
                            marked = True
                            break
                        i = i - 2
                    if not marked or -(i-2) > len(self.analytic_result):
                        all_zs = [zs for zs in self.analytic_result if type(zs) is ZhongShu]
                        all_first_xd = [zs.take_first_xd_as_zslx(direction) for zs in all_zs]
                        first_xd = sorted(all_first_xd, key=take_start_price, reverse=direction==TopBotType.top2bot)[0]
                        
                elif len(self.analytic_result) < 3 or self.analytic_result[-3].direction != last_xd.direction:
                    first_xd = zs.take_first_xd_as_zslx(direction)
                else:
                    first_xd = self.analytic_result[-3]
                    
                return first_xd, zs, last_xd
                
            else:
                print("Invalid Zou Shi type")
                return None, None, None
    
    def two_zhongshu_form_qvshi(self, zs1, zs2, zs_level=ZhongShuLevel.current):
        '''
        We are only dealing with current level of QV SHI by default, and the first ZS can be higher level 
        due to the rule of connectivity:
        two adjacent ZhongShu going in the same direction, or the first ZhongShu is complex(can be both direction)
        '''
        result = False
        if zs1.get_level().value == zs2.get_level().value == zs_level.value and\
            (zs1.direction == zs2.direction or zs1.is_complex_type()):
            [l1, u1] = zs1.get_amplitude_region_original()
            [l2, u2] = zs2.get_amplitude_region_original()
            if l1 > u2 or l2 > u1: # two Zhong Shu without intersection
                if self.isdebug:
                    print("1 current Zou Shi is QV SHI \n{0} \n{1}".format(zs1, zs2))
                result = True        
        
        # if the first ZhongShu is complex and can be split to form QvShi with second ZhongShu
        if not result and zs1.get_level().value > zs2.get_level().value == zs_level.value and\
            (zs1.direction == zs2.direction or zs1.is_complex_type()):
            split_nodes = zs1.get_split_zs(zs2.direction)
            if len(split_nodes) >= 5:
                new_zs = ZhongShu(split_nodes[1], split_nodes[2], split_nodes[3], split_nodes[4], zs2.direction, zs2.original_df)
                new_zs.add_new_nodes(split_nodes[5:])
    
                [l1, u1] = new_zs.get_amplitude_region_original()
                [l2, u2] = zs2.get_amplitude_region_original()
                if l1 > u2 or l2 > u1: # two Zhong Shu without intersection
                    if self.isdebug:
                        print("2 current Zou Shi is QV SHI \n{0} \n{1}".format(zs1, zs2))
                    result = True
        return result
    
    def two_zslx_interact(self, zs1, zs2):
        result = False
        [l1, u1] = zs1.get_amplitude_region()
        [l2, u2] = zs2.get_amplitude_region()
        return l1 <= l2 <= u1 or l1 <= u2 <= u1 or l2 <= l1 <= u2 or l2 <= u1 <= u2
    
    def two_zslx_interact_original(self, zs1, zs2):
        result = False
        [l1, u1] = zs1.get_amplitude_region_original()
        [l2, u2] = zs2.get_amplitude_region_original()
        return l1 <= l2 <= u1 or l1 <= u2 <= u1 or l2 <= l1 <= u2 or l2 <= u1 <= u2
    
    def check_zoushi_status(self):
        # check if current status beichi or panzhengbeichi
        recent_zoushi = self.analytic_result[-5:] # 5 should include all cases
        recent_zhongshu = []
        for zs in recent_zoushi:
            if type(zs) is ZhongShu:
                recent_zhongshu.append(zs)
        
        if len(recent_zhongshu) < 2:
            self.isQvShi = False
            if self.isdebug:
                print("less than two zhong shu")
            return
        
        # STARDARD CASE: 
        self.isQvShi = self.two_zhongshu_form_qvshi(recent_zhongshu[-2], recent_zhongshu[-1]) 
        if self.isQvShi:
            if self.isdebug:
                print("QU SHI 1")
            return self.isQvShi
        
        # TWO ZHONG SHU followed by ZHONGYIN ZHONGSHU
        # first two zhong shu no interaction
        # last zhong shu interacts with second, this is for TYPE II trade point
        if len(recent_zhongshu) >= 3 and\
            (recent_zhongshu[-2].direction == recent_zhongshu[-1].direction) and\
            (not recent_zhongshu[-1].is_complex_type()):
            first_two_zs_qs = self.two_zhongshu_form_qvshi(recent_zhongshu[-3], recent_zhongshu[-2])
            second_third_interact = self.two_zslx_interact_original(recent_zhongshu[-2], recent_zhongshu[-1])
            self.isQvShi = first_two_zs_qs and second_third_interact
            if self.isQvShi and self.isdebug:
                print("QU SHI 2")
        else:
            self.isQvShi = False
            
        if self.isQvShi and self.isDescription:
            print("QU SHI FOUND")
        return self.isQvShi


        
    def define_equilibrium(self, direction, check_tb_structure=False, check_xd_exhaustion=False):
        if len(self.analytic_result) < 2: # if we don't have enough data, return False directly
            if self.isdebug:
                print("Not enough DATA define_equilibrium")
            return False
        a, _, c = self.find_most_recent_zoushi(direction)
        
        return self.check_exhaustion(a, c, 
                                     check_tb_structure=check_tb_structure, 
                                     check_xd_exhaustion=check_xd_exhaustion)
        
    def check_exhaustion(self, zslx_a, zslx_c, check_tb_structure=False, check_xd_exhaustion=False):
        exhaustion_result = False
        if zslx_a is None or zslx_c is None or zslx_a.isEmpty() or zslx_c.isEmpty():
            if self.isdebug:
                print("Not enough DATA check_exhaustion")
            return exhaustion_result
        
        if check_tb_structure:
            a_s = zslx_a.get_tb_structure() 
            c_s =zslx_c.get_tb_structure()
            if a_s[0] != c_s[0] or a_s[-1] != c_s[-1]:
                if self.isdebug:
                    print("Not matching ZSLX structure")
                return exhaustion_result
        
        if int(zslx_a.get_magnitude() - zslx_c.get_magnitude()) != 0:
            if self.isdebug:
                print("Not matching magnitude")
            return exhaustion_result
        
        zslx_slope = zslx_a.work_out_slope()
        
        latest_slope = zslx_c.work_out_slope()

        if np.sign(latest_slope) == 0 or np.sign(zslx_slope) == 0:
            if self.isdebug:
                print("Invalid slope {0}, {1}".format(zslx_slope, latest_slope))
            return exhaustion_result
        
        if np.sign(latest_slope) == np.sign(zslx_slope) and abs(latest_slope) < abs(zslx_slope):
            if self.isdebug or self.isDescription:
                print("exhaustion found by reduced slope: {0} {1}".format(zslx_slope, latest_slope))
            exhaustion_result = True

        if not exhaustion_result and self.isQvShi: # if QV SHI => at least two Zhong Shu, We could also use macd for help
            zslx_macd = zslx_a.get_macd_acc()
            latest_macd = zslx_c.get_macd_acc()
            exhaustion_result = abs(zslx_macd) > abs(latest_macd)
            if self.isdebug or self.isDescription:
                print("{0} found by macd: {1}, {2}".format("exhaustion" if exhaustion_result else "exhaustion not", zslx_macd, latest_macd))
            
        
        if exhaustion_result and check_xd_exhaustion:
            exhaustion_result = zslx_c.check_exhaustion()
            if self.isdebug or self.isDescription:
                print("{0} found at XD level".format("exhaustion" if exhaustion_result else "exhaustion not"))
        return exhaustion_result
         
    def check_chan_type(self, check_end_tb=False):
        '''
        This method determines potential TYPE of trade point under CHAN
        '''
        all_types = []
        if len(self.analytic_result) < 2:
#             all_types.append((Chan_Type.INVALID, TopBotType.noTopBot, 0))
            return all_types
        
        # SIMPLE CASE
        if self.isQvShi:
            # I current Zou Shi must end
            if type(self.analytic_result[-1]) is ZouShiLeiXing: # last zslx escape last zhong shu
                zslx = self.analytic_result[-1]
                zs = self.analytic_result[-2]
                zslx2= self.analytic_result[-3]
                [lc, uc] = zs.get_core_region()
                if zslx.direction == zslx2.direction:
                    if check_end_tb:
                        if zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.bot:
                            if self.isdebug:
                                print("TYPE I trade point 1")
                            all_types.append((Chan_Type.I, TopBotType.top2bot, lc))
                        elif zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.top:
                            if self.isdebug:
                                print("TYPE I trade point 2")
                            all_types.append((Chan_Type.I, TopBotType.bot2top, uc))
                    else:
                        if self.isdebug:
                            print("TYPE I trade point 3")
                        all_types.append((Chan_Type.I, zslx.direction, lc if zslx.direction==TopBotType.top2bot else uc))
            
            if type(self.analytic_result[-1]) is ZhongShu: # last XD in zhong shu must make top or bot
                zs = self.analytic_result[-1]
                [l,u] = zs.get_amplitude_region_original()
                [lc, uc] = zs.get_core_region()
                if zs.is_complex_type() and len(zs.extra_nodes) >= 1:
                    if zs.extra_nodes[-1].tb == TopBotType.bot and\
                        zs.direction == TopBotType.top2bot and\
                        zs.extra_nodes[-1].chan_price == l:
                        if self.isdebug:
                            print("TYPE I trade point 3")
                        all_types.append((Chan_Type.I, TopBotType.top2bot, lc))
                    elif zs.direction == TopBotType.bot2top and\
                        zs.extra_nodes[-1].tb == TopBotType.top and\
                        zs.extra_nodes[-1].chan_price == u:
                        all_types.append((Chan_Type.I, TopBotType.bot2top, uc))
                        if self.isdebug:
                            print("TYPE I trade point 4")

            # II Zhong Yin Zhong Shu must form
            # case of return into last QV shi Zhong shu
            if type(self.analytic_result[-1]) is ZhongShu: # Type I return into core region
                zs = self.analytic_result[-1]
                if zs.is_complex_type() and len(zs.extra_nodes) >= 3:
                    core_region = zs.get_core_region()
                    if (zs.extra_nodes[-3].chan_price > core_region[1] and\
                        zs.extra_nodes[-2].chan_price <= core_region[1] and\
                        zs.extra_nodes[-1].chan_price > core_region[1] and\
                        zs.direction == TopBotType.bot2top) or\
                        (zs.extra_nodes[-3].chan_price < core_region[0] and\
                         zs.extra_nodes[-2].chan_price >= core_region[0] and\
                         zs.extra_nodes[-1].chan_price < core_region[0] and\
                         zs.direction == TopBotType.top2bot):
                            if check_end_tb:
                                if ((zs.extra_nodes[-1].tb == TopBotType.top and zs.direction == TopBotType.bot2top) or\
                                    (zs.extra_nodes[-1].tb == TopBotType.bot and zs.direction == TopBotType.top2bot)):
                                    all_types.append((Chan_Type.II, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
                                    if self.isdebug:
                                        print("TYPE II trade point 1")                            
                            else:
                                all_types.append((Chan_Type.II, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
                                if self.isdebug:
                                    print("TYPE II trade point 2")

            # case of return into last QV shi amplitude zhong yin zhongshu about to form
            # simple case where weak III short forms.
            if type(self.analytic_result[-1]) is ZouShiLeiXing:
                zs = self.analytic_result[-2]
                zslx = self.analytic_result[-1]
                if zs.direction == zslx.direction and\
                    len(zslx.zoushi_nodes) >= 3:
                    core_region = zs.get_core_region()
                    amplitude_region = zs.get_amplitude_region_original()  
                    if (zslx.zoushi_nodes[-3].chan_price > core_region[1] and\
                        zslx.zoushi_nodes[-2].chan_price <= amplitude_region[1] and\
                        zslx.zoushi_nodes[-1].chan_price > core_region[1] and\
                        zs.direction == TopBotType.bot2top) or\
                        (zslx.zoushi_nodes[-3].chan_price < core_region[0] and\
                         zslx.zoushi_nodes[-2].chan_price >= amplitude_region[0] and\
                         zslx.zoushi_nodes[-1].chan_price < core_region[0] and\
                         zs.direction == TopBotType.top2bot):     
                            if check_end_tb:
                                if ((zslx.zoushi_nodes[-1].tb == TopBotType.top and zs.direction == TopBotType.bot2top) or\
                                    (zslx.zoushi_nodes[-1].tb == TopBotType.bot and zs.direction == TopBotType.top2bot)):
                                    all_types.append((Chan_Type.II_weak, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
                                    if self.isdebug:
                                        print("TYPE II trade point 3")                            
                            else:
                                all_types.append((Chan_Type.II_weak, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
                                if self.isdebug:
                                    print("TYPE II trade point 4")                        
                        
        # III current Zhong Shu must end, simple case
        if type(self.analytic_result[-1]) is ZouShiLeiXing:
            zslx = self.analytic_result[-1]
            zs = self.analytic_result[-2]
            core_region = zs.get_core_region()
            amplitude_region_original = zs.get_amplitude_region_original()
            
            if len(zslx.zoushi_nodes) == 3 and\
                (zslx.zoushi_nodes[-1].chan_price < amplitude_region_original[0] or zslx.zoushi_nodes[-1].chan_price > amplitude_region_original[1]):
                if not check_end_tb or\
                    (zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.top) or\
                   (zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.bot):
                    type_direction = TopBotType.top2bot if zslx.zoushi_nodes[-1].tb == TopBotType.bot else TopBotType.bot2top,
                    all_types.append((Chan_Type.III, 
                                      type_direction,
                                      core_region[1] if type_direction == TopBotType.top2bot else core_region[0]))
                    if self.isdebug:
                        print("TYPE III trade point 1")
            elif len(zslx.zoushi_nodes) == 3 and\
                (zslx.zoushi_nodes[-1].chan_price < core_region[0] or zslx.zoushi_nodes[-1].chan_price > core_region[1]):
                if not check_end_tb or\
                    (zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.top) or\
                   (zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.bot):                
                    type_direction = TopBotType.top2bot if zslx.zoushi_nodes[-1].tb == TopBotType.bot else TopBotType.bot2top
                    all_types.append((Chan_Type.III_weak,
                                      type_direction,
                                      core_region[1] if type_direction == TopBotType.top2bot else core_region[0]))
                    if self.isdebug:
                        print("TYPE III trade point 2")
            
            # a bit more complex type than standard two XD away and not back case, no new zs formed        
            split_direction, split_nodes = zslx.get_reverse_split_zslx()
            pure_zslx = ZouShiLeiXing(split_direction, self.original_df, split_nodes)
            # at least two split nodes required to form a zslx
            if len(split_nodes) >= 2 and not self.two_zslx_interact_original(zs, pure_zslx):
                if not check_end_tb or\
                ((pure_zslx.direction == TopBotType.top2bot and pure_zslx.zoushi_nodes[-1].tb == TopBotType.bot) and\
                (pure_zslx.direction == TopBotType.bot2top and pure_zslx.zoushi_nodes[-1].tb == TopBotType.top)):
                    all_types.append((Chan_Type.III,
                                      pure_zslx.direction,
                                      core_region[1] if pure_zslx.direction == TopBotType.top2bot else core_region[0]))
                    if self.isdebug:
                        print("TYPE III trade point 7")
        
        # TYPE III where zslx form reverse direction zhongshu, and last XD of new zhong shu didn't go back 
        if len(self.analytic_result) >= 3 and type(self.analytic_result[-1]) is ZhongShu:
            pre_zs = self.analytic_result[-3]
            zslx = self.analytic_result[-2]
            now_zs = self.analytic_result[-1]
            core_region = pre_zs.get_core_region()
            if not now_zs.is_complex_type():
                if not check_end_tb or\
                ((now_zs.forth.tb == TopBotType.bot and now_zs.direction == TopBotType.bot2top) or\
                 (now_zs.forth.tb == TopBotType.top and now_zs.direction == TopBotType.top2bot)): # reverse type here
                    if not self.two_zslx_interact_original(pre_zs, now_zs):
                        all_types.append((Chan_Type.III, 
                                          TopBotType.top2bot if now_zs.direction == TopBotType.bot2top else TopBotType.bot2top,
                                          core_region[1] if now_zs.direction == TopBotType.bot2top else core_region[0]))
                        if self.isdebug:
                            print("TYPE III trade point 3")
                    elif not self.two_zslx_interact(pre_zs, now_zs):
                        all_types.append((Chan_Type.III_weak, 
                                          TopBotType.top2bot if now_zs.direction == TopBotType.bot2top else TopBotType.bot2top,
                                          core_region[1] if now_zs.direction == TopBotType.bot2top else core_region[0]))
                        if self.isdebug:
                            print("TYPE III trade point 4")
                
        # TYPE III two reverse direction zslx, with new reverse direction zhongshu in the middle
        if len(self.analytic_result) >= 4 and type(self.analytic_result[-1]) is ZouShiLeiXing:
            latest_zslx = self.analytic_result[-1]
            now_zs = self.analytic_result[-2]
            pre_zs = self.analytic_result[-4]
            core_region = pre_zs.get_core_region()
            if not self.two_zslx_interact_original(pre_zs, latest_zslx) and\
                latest_zslx.direction != now_zs.direction and\
                not now_zs.is_complex_type():
                if not check_end_tb or\
                ((latest_zslx.zoushi_nodes[-1].tb == TopBotType.top and latest_zslx.direction == TopBotType.bot2top) or\
                 (latest_zslx.zoushi_nodes[-1].tb == TopBotType.bot and latest_zslx.direction == TopBotType.top2bot)):
                    all_types.append((Chan_Type.III, 
                                      latest_zslx.direction,
                                      core_region[1] if latest_zslx.direction == TopBotType.top2bot else core_region[0]))
                    if self.isdebug:
                        print("TYPE III trade point 5")
            if not self.two_zslx_interact(pre_zs, latest_zslx) and\
                latest_zslx.direction != now_zs.direction and\
                not now_zs.is_complex_type():
                if not check_end_tb or\
                ((latest_zslx.zoushi_nodes[-1].tb == TopBotType.top and latest_zslx.direction == TopBotType.bot2top) or\
                 (latest_zslx.zoushi_nodes[-1].tb == TopBotType.bot and latest_zslx.direction == TopBotType.top2bot)):            
                    all_types.append((Chan_Type.III_weak, 
                                      latest_zslx.direction,
                                      core_region[1] if latest_zslx.direction == TopBotType.top2bot else core_region[0]))
                    if self.isdebug:
                        print("TYPE III trade point 6")
        all_types = list(set(all_types))
        if all_types and (self.isDescription or self.isdebug):
            print("all chan types found: {0}".format(all_types))

        return all_types
    
    
class NestedInterval():            
    '''
    This class utilize BEI CHI and apply them to multiple nested levels, 
    existing level goes:
    current_level -> XD -> BI
    periods goes from high to low level
    '''
    def __init__(self, stock, end_dt, periods, count=2000, isdebug=False, isDescription=True, isAnal=True):
        self.stock = stock
        self.end_dt = end_dt
        self.periods = periods
        self.count = count
        self.is_anal = isAnal

        self.isdebug = isdebug
        self.isDescription = isDescription

        self.df_zoushi_tuple_list = []  
        
        self.prepare_data()
    
    def prepare_data(self):
        for pe in self.periods:
            if self.is_anal:
                stock_df = get_price(self.stock, count=self.count, end_date=self.end_dt, frequency=pe,fields= ['open',  'high', 'low','close'],skip_paused=True)
            else:
                stock_df = attribute_history(self.stock, count=self.count, unit=pe,fields= ['open',  'high', 'low','close'],skip_paused=True)
            kb_df = KBarProcessor(stock_df, isdebug=self.isdebug)
            xd_df = kb_df.getIntegradedXD()
            crp_df = CentralRegionProcess(xd_df, isdebug=self.isdebug, use_xd=True)
            anal_zoushi = crp_df.define_central_region()
            self.df_zoushi_tuple_list.append((xd_df,anal_zoushi))
    
    def analyze_zoushi(self, direction, chan_type = Chan_Type.INVALID):
        '''
        The code original designed for more than two levels
        1. check high level chan type
        2. check sub level exhaustion
        return value:
        a. At current two level trading point
        b. top level chan types
        '''
        
        anal_result = True
        if self.isdebug:
            print("looking for {0} at top level {1} point with type:{2}".format("long" if direction == TopBotType.top2bot else "short",
                                                                      self.periods[0],
                                                                      chan_type))
        # high level
        xd_df, anal_zoushi = self.df_zoushi_tuple_list[0]
        if anal_zoushi is None:
            return False, []
        eq = Equilibrium(xd_df, anal_zoushi.zslx_result, isdebug=self.isdebug, isDescription=self.isDescription)
        chan_types = eq.check_chan_type(check_end_tb=False)
        if not chan_types:
            return False, chan_types
        for _, chan_d,_ in chan_types: # early checks if we have any types found with opposite direction, no need to go further
            if chan_d != direction:
                if self.isdebug:
                    print("opposite direction chan type found")
                return False, chan_types
        
        for chan_t, chan_d, chan_p in chan_types:
            high_exhausted = ((chan_t in chan_type) if type(chan_type) is list else (chan_t == chan_type)) and\
                            (eq.define_equilibrium(direction, check_tb_structure=False, check_xd_exhaustion=False) if chan_t == Chan_Type.I else True)
            if self.isDescription or self.isdebug:
                print("Top level {0} {1} {2} with price level: {3}".format(self.periods[0], 
                                                                           chan_d, 
                                                                           "ready" if high_exhausted else "not ready",
                                                                           chan_p))
            if not high_exhausted:
                return False, chan_types

            split_time = anal_zoushi.sub_zoushi_time(chan_t, chan_d)
            if self.isdebug:
                print("split time at {0}".format(split_time))
            
            i = 1
            while i < len(self.df_zoushi_tuple_list):
                if self.isdebug:
                    print("looking for {0} at top level {1} point with type:{2}".format("long" if direction == TopBotType.top2bot else "short",
                                                                              self.periods[i],
                                                                              chan_t))
                xd_df_low, anal_zoushi_low = self.df_zoushi_tuple_list[i]
                if anal_zoushi_low is None:
                    return False, chan_types
                split_anal_zoushi_result = anal_zoushi_low.split_by_time(split_time)
                eq = Equilibrium(xd_df_low, split_anal_zoushi_result, isdebug=self.isdebug, isDescription=self.isDescription)
                low_exhausted = eq.define_equilibrium(direction, check_tb_structure=True, check_xd_exhaustion=True)
                if self.isDescription or self.isdebug:
                    print("Sub level {0} {1} {2}".format(self.periods[i], eq.isQvShi,"exhausted" if low_exhausted else "continues"))
                if not low_exhausted:
                    return False, chan_types
                # update split time for next level
                i = i + 1
                if i < len(self.df_zoushi_tuple_list):
                    split_time = anal_zoushi_low.sub_zoushi_time(Chan_Type.INVALID, direction)
        return anal_result, chan_types
    
    def indepth_analyze_zoushi(self, direction):
        '''
        specifically used to gauge the smallest level of precision, check at BI level
        '''
        xd_df, anal_zoushi_xd = self.df_zoushi_tuple_list[0]
        
        split_time = anal_zoushi_xd.sub_zoushi_time(Chan_Type.INVALID, direction)
        
        if self.isdebug:
            print("XD split time at:{0}".format(split_time))
        
        crp_df = CentralRegionProcess(xd_df, isdebug=self.isdebug, use_xd=False)
        anal_zoushi_bi = crp_df.define_central_region()
        
        split_anal_zoushi_bi = anal_zoushi_bi.split_by_time(split_time)
        
        eq = Equilibrium(xd_df, split_anal_zoushi_bi, isdebug=self.isdebug, isDescription=self.isDescription)
        bi_exhausted = eq.define_equilibrium(direction, check_tb_structure=True, check_xd_exhaustion=True)
        if (self.isdebug or self.isDescription) and bi_exhausted:
            print("BI level exhausted")
        
        return bi_exhausted

    def full_check_zoushi(self, period, direction, check_end_tb=False, check_tb_structure=False, check_xd_exhaustion=False, split_time=None):
        '''
        return current level:
        a exhausted(bool)
        b chan type/price level
        c split time
        '''
        if self.isdebug:
            print("looking for {0} at top level {1}".format("long" if direction == TopBotType.top2bot else "short",
                                                            period))
        current_pe_index = self.periods.index(period)
        xd_df, anal_zoushi = self.df_zoushi_tuple_list[current_pe_index]
        chan_types = [(Chan_Type.INVALID, TopBotType.noTopBot, 0)]# default value
        if anal_zoushi is None:
            return False, chan_types, None
        
        eq = Equilibrium(xd_df, 
                         anal_zoushi.split_by_time(split_time) if split_time is not None else anal_zoushi.zslx_result, 
                         isdebug=self.isdebug, 
                         isDescription=self.isDescription)
        top_chan_types = eq.check_chan_type(check_end_tb=check_end_tb)
        if not top_chan_types:
            return False, chan_types, None
        else:
            chan_types = top_chan_types
        
        for _, chan_d, _ in chan_types: # early checks if we have any types found with opposite direction, no need to go further
            if chan_d != direction:
                if self.isdebug:
                    print("opposite direction chan type found")
                return False, chan_types, None
        
        # only type II and III can coexist, only need to check the first one
        # reverse direction case are dealt above
        chan_t, chan_d, chan_p = chan_types[0] 
        exhausted = eq.define_equilibrium(direction, check_tb_structure=check_tb_structure, check_xd_exhaustion=check_xd_exhaustion) if chan_t == Chan_Type.I else True
        if self.isDescription or self.isdebug:
            print("current level {0} {1} {2}".format(self.periods[0], chan_d, "ready" if exhausted else "not ready"))
        if not exhausted:
            return False, chan_types, None
        else:
            splitTime = anal_zoushi.sub_zoushi_time(chan_t, chan_d)
            return True, chan_types, splitTime