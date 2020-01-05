from biaoLiStatus import * 
from kBarProcessor import *
from centralRegion import *

import numpy as np
import pandas as pd


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
        working_df = self.original_xd_df        
        
        working_df = self.prepare_df_data(working_df)
        
        init_idx, init_d = self.find_initial_direction(working_df)
        
        if init_d == TopBotType.noTopBot: # not enough data, we don't do anything
            if self.isdebug:
                print("not enough data, return define_central_region")
            return []
        
        self.zoushi = self.find_central_region(init_idx, init_d, working_df)
            
        return self.zoushi.zslx_result
        
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
            print("working_df: {0}".format(working_df.head(10)[['chan_price', tb_name, 'new_index','macd_acc_'+tb_name]]))
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
    
    def find_most_recent_zoushi(self):
        '''
        Make sure we return the most recent Zhong Shu and the Zou Shi Lei Xing Entering it.
        The Zou Shi Lei Xing Exiting it will be reworked on the original df
        '''
        if type(self.analytic_result[-1]) is ZhongShu and self.analytic_result[-1].is_complex_type():
            filled_zslx = self.analytic_result[-1].take_last_xd_as_zslx()
            return self.analytic_result[-2], self.analytic_result[-1], filled_zslx
        elif type(self.analytic_result[-1]) is ZouShiLeiXing and len(self.analytic_result) >= 3:
            return self.analytic_result[-3], self.analytic_result[-2], self.analytic_result[-1]
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
        if zs1.get_level().value >= zs2.get_level().value == zs_level and\
            (zs1.direction == zs2.direction or zs2.is_complex_type()):
            [l1, u1] = zs1.get_amplitude_region_original()
            [l2, u2] = zs2.get_amplitude_region_original()
            if l1 > u2 or l2 > u1: # two Zhong Shu without intersection
                if self.isdebug:
                    print("current Zou Shi is QV SHI \n{0} \n{1}".format(zs1, zs2))
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
        
    def define_equilibrium(self):        
        if len(self.analytic_result) < 2: # if we don't have enough data, return False directly
            if self.isdebug:
                print("Not enough DATA define_equilibrium")
            return False
        a, B, c = self.find_most_recent_zoushi()
        
        return self.check_exhaustion(a, B, c)
        
    def check_exhaustion(self, zslx_a, zs_B, zslx_c):
        if zslx_a is None or zslx_c is None:
            if self.isdebug:
                print("Not enough DATA check_exhaustion")
            return False
        
        zslx_slope = zslx_a.work_out_slope()
        
        latest_slope = zslx_c.work_out_slope()

        if np.sign(latest_slope) == 0 or np.sign(zslx_slope) == 0:
            if self.isdebug:
                print("Invalid slope {0}, {1}".format(zslx_slope, latest_slope))
            return False
        
        if np.sign(latest_slope) == np.sign(zslx_slope) and abs(latest_slope) < abs(zslx_slope):
            if self.isdebug or self.isDescription:
                print("exhaustion found by reduced slope: {0} {1}".format(zslx_slope, latest_slope))
            return True

        if self.isQvShi: # if QV SHI => at least two Zhong Shu, We could also use macd for help
            zslx_macd = zslx_a.get_macd_acc()
            latest_macd = zslx_c.get_macd_acc()
            return abs(zslx_macd) > abs(latest_macd)
        
        # TODO check zslx exhaustion
#         latest_slope.check_exhaustion()
        return False
         
    def check_chan_type(self):
        '''
        This method determines potential TYPE of trade point under CHAN
        '''
        all_types = []
        if len(self.analytic_result) < 3:
            all_types.append((Chan_Type.INVALID, TopBotType.noTopBot))
            return all_types
        
        # SIMPLE CASE
        if self.isQvShi:
            # I current Zou Shi must end
            if type(self.analytic_result[-1]) is ZouShiLeiXing: # last zslx escape last zhong shu
                zslx = self.analytic_result[-1]
                if zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.bot:
                    if self.isdebug:
                        print("TYPE I trade point 1")
                    all_types.append((Chan_Type.I, TopBotType.top2bot))
                elif zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.top:
                    if self.isdebug:
                        print("TYPE I trade point 1")
                    all_types.append((Chan_Type.I, TopBotType.bot2top))
            
            if type(self.analytic_result[-1]) is ZhongShu: # last XD in zhong shu must make top or bot
                zs = self.analytic_result[-1]
                [l,u] = zs.get_amplitude_region_original()
                if zs.is_complex_type() and len(zs.extra_nodes) == 1:
                    if zs.direction == TopBotType.top2bot and\
                        zs.extra_nodes[-1].tb == TopBotType.bot and\
                        zs.extra_nodes[-1].chan_price == l:
                        if self.isdebug:
                            print("TYPE I trade point 3")
                        all_types.append((Chan_Type.I, TopBotType.top2bot))
                    elif zs.direction == TopBotType.bot2top and\
                        zs.extra_nodes[-1].tb == TopBotType.top and\
                        zs.extra_nodes[-1].chan_price == u:
                        all_types.append((Chan_Type.I, TopBotType.bot2top))
                        if self.isdebug:
                            print("TYPE I trade point 4")

            # II Zhong Yin Zhong Shu must form
            if type(self.analytic_result[-1]) is ZhongShu: # Type I return into core region
                zs = self.analytic_result[-1]
                if zs.is_complex_type() and len(zs.extra_nodes) >= 3:
                    core_region = zs.get_core_region()
                    amplitude_region = zs.get_amplitude_region_original()
                    if zs.extra_nodes[-3].chan_price > core_region[1] or zs.extra_nodes[-3].chan_price < core_region[0]:
                        if zs.extra_nodes[-1].chan_price > core_region[1] or zs.extra_nodes[-1].chan_price < core_region[0]:
                            all_types.append((Chan_Type.II, TopBotType.top2bot if zs.extra_nodes[-1].tb == TopBotType.bot else TopBotType.bot2top))
                            if self.isdebug:
                                print("TYPE II trade point 1")
                            
                    
        # III current Zhong Shu must end, simple case
        if type(self.analytic_result[-1]) is ZouShiLeiXing:
            zslx = self.analytic_result[-1]
            zs = self.analytic_result[-2]
            core_region = zs.get_core_region()
            amplitude_region_original = zs.get_amplitude_region_original()
            
            if len(zslx.zoushi_nodes) == 3 and\
                (zslx.zoushi_nodes[-1].chan_price < amplitude_region_original[0] or zslx.zoushi_nodes[-1].chan_price > amplitude_region_original[1]):
                if (zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.top) or\
                   (zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.bot):
                    all_types.append((Chan_Type.III, TopBotType.top2bot if zslx.zoushi_nodes[-1].tb == TopBotType.bot else TopBotType.bot2top))
                    if self.isdebug:
                        print("TYPE III trade point 1")
            elif len(zslx.zoushi_nodes) == 3 and\
                (zslx.zoushi_nodes[-1].chan_price < core_region[0] or zslx.zoushi_nodes[-1].chan_price > core_region[1]):
                if (zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.top) or\
                   (zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.bot):                
                    all_types.append((Chan_Type.III_weak, TopBotType.top2bot if zslx.zoushi_nodes[-1].tb == TopBotType.bot else TopBotType.bot2top))
                    if self.isdebug:
                        print("TYPE III trade point 2")
                    
            # a bit more complex type than standard two XD away and not back case, no new zs formed        
            split_direction, split_nodes = zslx.get_reverse_split_zslx()
            pure_zslx = ZouShiLeiXing(split_direction, self.original_df, split_nodes)
            # at least two split nodes required to form a zslx
            if len(split_nodes) >= 2 and not self.two_zslx_interact_original(zs, pure_zslx):
                all_types.append((Chan_Type.III, pure_zslx.direction))
                if self.isdebug:
                    print("TYPE III trade point 7")
        
        # TYPE III where zslx form reverse direction zhongshu, and last XD of new zhong shu didn't go back 
        if len(self.analytic_result) >= 3 and type(self.analytic_result[-1]) is ZhongShu:
            pre_zs = self.analytic_result[-3]
            zslx = self.analytic_result[-2]
            now_zs = self.analytic_result[-1]            

            if not now_zs.is_complex_type() and\
                ((now_zs.forth.tb == TopBotType.bot and now_zs.direction == TopBotType.bot2top) or\
                 (now_zs.forth.tb == TopBotType.top and now_zs.direction == TopBotType.top2bot)): # reverse type here
                if not self.two_zslx_interact_original(pre_zs, now_zs):
                    all_types.append((Chan_Type.III, TopBotType.top2bot if now_zs.direction == TopBotType.bot2top else TopBotType.bot2top))
                    if self.isdebug:
                        print("TYPE III trade point 3")
                elif not self.two_zslx_interact(pre_zs, now_zs):
                    all_types.append((Chan_Type.III_weak, TopBotType.top2bot if now_zs.direction == TopBotType.bot2top else TopBotType.bot2top))
                    if self.isdebug:
                        print("TYPE III trade point 4")                    
                
        # TYPE III two reverse direction zslx, with new reverse direction zhongshu in the middle
        if len(self.analytic_result) >= 4 and type(self.analytic_result[-1]) is ZouShiLeiXing:
            latest_zslx = self.analytic_result[-1]
            now_zs = self.analytic_result[-2]
            pre_zs = self.analytic_result[-4]
            if not self.two_zslx_interact_original(pre_zs, latest_zslx) and\
                latest_zslx.direction != now_zs.direction and\
                not now_zs.is_complex_type():
                all_types.append((Chan_Type.III, latest_zslx.direction))
                if self.isdebug:
                    print("TYPE III trade point 5")   
            if not self.two_zslx_interact(pre_zs, latest_zslx) and\
                latest_zslx.direction != now_zs.direction and\
                not now_zs.is_complex_type():
                all_types.append((Chan_Type.III_weak, latest_zslx.direction))
                if self.isdebug:
                    print("TYPE III trade point 6")                             
            
                
        if all_types and (self.isDescription or self.isdebug):
            print("all chan types found: {0}".format(all_types))
            
        return all_types
    
    
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
        anal_result = crp.define_central_region()
        
        if not anal_result:
            if self.isdebug:
                print("not enough data analyze_zoushi")
            return False, TopBotType.noTopBot
        
        eq = Equilibrium(self.df_xd_bi, anal_result, self.isdebug)
        return eq.define_equilibrium(), anal_result[-1].direction
    
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


        
                