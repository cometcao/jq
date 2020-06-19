try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *

from biaoLiStatus import * 
from kBar_Chan import *
from centralRegion import *
from chan_common_include import *
import datetime
import numpy as np
import pandas as pd

def work_out_count(start_dt, end_dt, unit):
    if type(start_dt) is str:
        start_dt = datetime.datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
    if type(end_dt) is str:
        end_dt = datetime.datetime.strptime(end_dt, "%Y-%m-%d %H:%M:%S")
        if end_dt.hour < 9:
            end_dt = (end_dt - datetime.timedelta(days = 1)).replace(hour=15, minute=0)
        elif end_dt.hour > 14:
            end_dt = end_dt.replace(hour=15, minute=0)

    start_time_delta = start_dt.replace(hour=15, minute=0) - start_dt if start_dt.hour >= 13 else start_dt.replace(hour=13, minute=30) - start_dt
    end_time_delta = end_dt - end_dt.replace(hour=9, minute=30) if end_dt.hour <= 11 else end_dt - end_dt.replace(hour=11, minute=0)
    
    trade_days = get_trade_days(start_date=start_dt.date(), end_date=end_dt.date())
    day_diff = len(trade_days) - 2
    time_delta_seconds = start_time_delta.total_seconds() + end_time_delta.total_seconds() + day_diff * 4 * 60 * 60

    if unit == '1d':
        count = np.ceil(time_delta_seconds / (60*30*8))
    elif unit == '30m':
        count = np.ceil(time_delta_seconds / (60*30))
    elif unit == '5m':
        count = np.ceil(time_delta_seconds / (60*5))
    elif unit == '1m':
        count = np.ceil(time_delta_seconds / 60)
    else:
        print("Unconventional unit, return 1000 for count")
        count = 1000
    count = count + 1 # inclusion for end_dt
    return count

def get_bars_new(security, 
                 unit='1d',
                 fields=['date', 'open','high','low','close'],
                 include_now=True, 
                 end_dt=None, 
                 start_dt=None, 
                 fq_ref_date=None, 
                 df=False):
    
    count = work_out_count(start_dt, end_dt, unit)

    return get_bars(security, 
                    count=int(count), 
                    unit=unit,
                    fields=fields,
                    include_now=include_now, 
                    end_dt=end_dt, 
                    fq_ref_date=fq_ref_date, 
                    df=df)


##############################################################################################################################

def check_chan_by_type_exhaustion(stock, 
                                  end_time, 
                                  periods, 
                                  count, 
                                  direction, 
                                  chan_type, 
                                  isdebug=False, 
                                  is_anal=False, 
                                  is_description=True,
                                  check_structure=False,
                                  check_full_zoushi=False,
                                  enable_composite=False):
    if is_description:
        print("check_chan_by_type_exhaustion working on stock: {0} at {1} on {2}".format(stock, periods, end_time))
    ni = NestedInterval(stock, 
                        end_dt=end_time, 
                        periods=periods, 
                        count=count, 
                        isdebug=isdebug, 
                        isDescription=is_description,
                        isAnal=is_anal)
    
    return ni.analyze_zoushi(direction, 
                             chan_type, 
                             check_end_tb=check_structure, 
                             check_tb_structure=check_structure,
                             check_full_zoushi=check_full_zoushi,
                             enable_composite=enable_composite)

def check_chan_indepth(stock, 
                       end_time, 
                       period, 
                       count, 
                       direction, 
                       isdebug=False, 
                       is_anal=False, 
                       is_description=True,
                       split_time=None,
                       check_full_zoushi=True,
                       ignore_bi_xd=True):
    if is_description:
        print("check_chan_indepth working on stock: {0} at {1} from {2} to {3}".format(stock, 
                                                                                       period,
                                                                                       split_time,
                                                                                       end_time))
    ni = NestedInterval(stock, 
                        end_dt=end_time, 
                        periods=[period], 
                        count=count, 
                        isdebug=isdebug, 
                        isDescription=is_description,
                        isAnal=is_anal,
                        use_xd=False,
                        initial_pe_prep=period,
                        initial_split_time=split_time)
    return ni.indepth_analyze_zoushi(direction, 
                                     split_time, 
                                     period, 
                                     force_zhongshu=True, 
                                     check_full_zoushi=check_full_zoushi,
                                     ignore_bi_xd=ignore_bi_xd)

def check_stock_sub(stock, 
                    end_time, 
                    periods, 
                    count=2000, 
                    direction=TopBotType.top2bot, 
                    chan_types=[Chan_Type.INVALID, Chan_Type.I], 
                    isdebug=False, 
                    is_anal=False, 
                    is_description=True,
                    split_time=None,
                    check_bi=False,
                    force_zhongshu=True,
                    allow_simple_zslx=True,
                    force_bi_zhongshu=True,
                    check_full_zoushi=True,
                    ignore_sub_xd=False):
    if is_description:
        print("check_stock_sub working on stock: {0} at {1} from {2} to {3}".format(stock, periods, split_time, end_time))
    ni = NestedInterval(stock, 
                        end_dt=end_time, 
                        periods=periods, 
                        count=count,
                        isdebug=isdebug, 
                        isDescription=is_description,
                        isAnal=is_anal, 
                        use_xd=True,
                        initial_pe_prep=periods[0],
                        initial_split_time=split_time, 
                        initial_direction=direction)

    pe = periods[0]
    exhausted, xd_exhausted, sub_profile = ni.full_check_zoushi(pe, 
                                                                 direction, 
                                                                 chan_types=chan_types,
                                                                 check_end_tb=True, 
                                                                 check_tb_structure=True,
                                                                 force_zhongshu=force_zhongshu,
                                                                 allow_simple_zslx=allow_simple_zslx,
                                                                 check_full_zoushi=check_full_zoushi, 
                                                                 ignore_sub_xd=ignore_sub_xd) # data split at retrieval time
    bi_split_time = sub_profile[0][5] # split time is the xd start time
    if exhausted and (ignore_sub_xd or xd_exhausted) and check_bi:
        bi_exhausted, bi_xd_exhausted, _, _ = ni.indepth_analyze_zoushi(direction, 
                                                                        bi_split_time, 
                                                                        pe, 
                                                                        force_zhongshu=force_bi_zhongshu,
                                                                        check_full_zoushi=check_full_zoushi,
                                                                        ignore_bi_xd=False) # never ignore bi level xd check
        return exhausted and bi_exhausted, (ignore_sub_xd or xd_exhausted) and bi_xd_exhausted, sub_profile, ni.completed_zhongshu()
    return exhausted, xd_exhausted, sub_profile, ni.completed_zhongshu()

def check_stock_full(stock, 
                     end_time, 
                     periods=['5m', '1m'], 
                     count=2000, 
                     direction=TopBotType.top2bot, 
                     current_chan_type=[Chan_Type.I, Chan_Type.III],
                     sub_chan_type=[Chan_Type.INVALID, Chan_Type.I],
                     isdebug=False, 
                     is_anal=False,
                     is_description=True,
                     sub_force_zhongshu=True,
                     sub_check_bi=False,
                     use_sub_split=True,
                     ignore_cur_xd=False, 
                     ignore_sub_xd=False):
    
    if is_description:
        print("check_stock_full working on stock: {0} at {1} on {2}".format(stock, periods, end_time))
    cur_pe = periods[0]
    sub_pe = periods[1]
    exhausted, xd_exhausted, chan_profile = check_chan_by_type_exhaustion(stock=stock, 
                                                                      end_time=end_time, 
                                                                      periods = [cur_pe], 
                                                                      count=count, 
                                                                      direction=direction, 
                                                                      chan_type=current_chan_type, 
                                                                      isdebug=isdebug, 
                                                                      is_description=is_description,
                                                                      check_structure=True,
                                                                      is_anal=is_anal,
                                                                      check_full_zoushi=False)
    if not chan_profile:
        chan_profile = [(Chan_Type.INVALID, TopBotType.noTopBot, 0, 0, 0, None, None)]

    # use the start of beichiduan
    splitTime = chan_profile[0][5] if use_sub_split else None# split time and force sub level with zhongshu formed
    
    if exhausted and (xd_exhausted or ignore_cur_xd) and sanity_check(stock, chan_profile, end_time, cur_pe, direction):
        sub_exhausted, sub_xd_exhausted, sub_profile, zhongshu_completed = check_stock_sub(stock=stock, 
                                                                                end_time=end_time, 
                                                                                periods=[sub_pe], 
                                                                                count=count, 
                                                                                direction=direction, 
                                                                                chan_types=sub_chan_type, 
                                                                                isdebug=isdebug, 
                                                                                is_anal=is_anal, 
                                                                                is_description=is_description,
                                                                                split_time=splitTime,
                                                                                check_bi=sub_check_bi,
                                                                                allow_simple_zslx=True,
                                                                                force_zhongshu=sub_force_zhongshu,
                                                                                force_bi_zhongshu=True,
                                                                                ignore_sub_xd=ignore_sub_xd,
                                                                                check_full_zoushi=False)
        chan_profile = chan_profile + sub_profile
        return exhausted and (xd_exhausted or ignore_cur_xd) and sub_exhausted and sub_xd_exhausted, chan_profile, zhongshu_completed
    else:
        return False, chan_profile, False

def sanity_check(stock, profile, end_time, pe, direction):
    # This method is used in case we provide the sub level check with initial direction while actual zoushi goes opposite
    # This will end up with invalid XD analysis in sub level
    # case: stock = '300760.XSHE' end_dt = '2019-07-01 14:30:00' period = ['5m', '1m']
    splitTime = profile[0][6]
    result = False
    stock_data = get_price(stock,
                          start_date=splitTime,
                          end_date=end_time, 
                          frequency='1m',
                          fields= ['close', 'low','low_limit'])
    
    if stock_data.iloc[-1, 0] > PRICE_UPPER_LIMIT:
        print("{0} price over {1}".format(stock, PRICE_UPPER_LIMIT))
        result = False
        # low_limit
#     if (stock_data.low == stock_data.low_limit).any():# touched low limit
#         print("{0} price reached low limit".format(stock))
#         return result
    
    if direction == TopBotType.top2bot:
        result = stock_data.iloc[0, 0] > stock_data.iloc[-1,0]
    elif direction == TopBotType.bot2top:
        result = stock_data.iloc[0, 0] < stock_data.iloc[-1,0]
    if not result:
        print("{0} failed sanity check on price".format(stock))
    return result
        
class CentralRegionProcess(object):
    '''
    This lib takes XD data, and the dataframe must contain chan_price, new_index, xd_tb, macd columns
    '''
    def __init__(self, tb_df, kbar_chan=None, isdebug=False, use_xd=True):
        self.tb_df = tb_df
        self.kbar_chan = kbar_chan
        self.use_xd = use_xd
        self.zoushi = None
        self.isdebug = isdebug

    def work_out_direction(self, first, second, third):
        assert first['tb'] == third['tb'], "Invalid tb information for direction"
        result_direction = TopBotType.noTopBot
        if first['tb'] == TopBotType.top.value and second['tb'] == TopBotType.bot.value:
            result_direction = TopBotType.bot2top if float_more(third['chan_price'], first['chan_price']) else TopBotType.top2bot
        elif first['tb'] == TopBotType.bot.value and second['tb'] == TopBotType.top.value:
            result_direction = TopBotType.bot2top if float_more(third['chan_price'], first['chan_price']) else TopBotType.top2bot
        else:
            print("Invalid tb data!!")
            
        return result_direction
    
    
    def find_initial_direction(self, working_df, initial_direction=TopBotType.noTopBot): 
        i = 0
        if working_df.size < 3:
            if working_df.size < 2:
                if self.isdebug:
                    print("not enough data for checking initial direction")
                return 0, TopBotType.noTopBot
            else: # 2 xd nodes
                first_node = working_df[0]
                second_node = working_df[1]
                assert first_node['tb'] != second_node['tb'], "Invalid xd tb data"
                return 0, TopBotType.top2bot if float_more(first_node['chan_price'], second_node['chan_price']) else TopBotType.bot2top
        
        if initial_direction != TopBotType.noTopBot:
            return 0, initial_direction
        
        first = working_df[i]
        second = working_df[i+1]
        third = working_df[i+2]
        
        initial_direction = self.work_out_direction(first, second, third)
        initial_loc = i
        
        if self.isdebug:
            print("initial direction: {0}, start datetime {1} loc {2}".format(initial_direction, working_df[i]['date'], initial_loc))
        return initial_loc, initial_direction
        
    
    def find_central_region(self, initial_loc, initial_direction, working_df):
        working_df = working_df[initial_loc:]
        
        zoushi = ZouShi([XianDuan_Node(working_df[i]) for i in range(working_df.size)], 
                        self.kbar_chan.getOriginal_df(),
                        isdebug=self.isdebug) if self.use_xd else\
                        ZouShi([BI_Node(working_df[i]) for i in range(working_df.size)], 
                               self.kbar_chan.getOriginal_df(), 
                               isdebug=self.isdebug)
        zoushi.analyze(initial_direction)

        return zoushi
    
    def define_central_region(self, initial_direction=TopBotType.noTopBot):
        '''
        We need fully integrated stock df with xd_tb, initial direction can be provided AFTER top level
        '''
        if self.tb_df.size==0:
            if self.isdebug:
                print("empty data, return define_central_region")
            return None
        working_df = self.tb_df
        
        try:
            working_df = self.prepare_df_data(working_df)
        except Exception as e:
            print("Error in data preparation:{0}".format(str(e)))
            return None
        
        init_loc, init_d = self.find_initial_direction(working_df, initial_direction)
        
        if init_d == TopBotType.noTopBot: # not enough data, we don't do anything
            if self.isdebug:
                print("not enough data, return define_central_region")
            return None
        
        self.zoushi = self.find_central_region(init_loc, init_d, working_df)
            
        return self.zoushi
        
    def convert_to_graph_data(self):
        '''
        We are assuming the Zou Shi is disassembled properly with data in timely order
        '''
        x_axis = []
        y_axis = []
        if self.zoushi is None:
            return x_axis, y_axis
        for zs in self.zoushi.zslx_result:
            if type(zs) is ZhongShu:
#                 print(zs)
                x_axis = x_axis + zs.get_core_time_region()
                y_axis = y_axis + zs.get_core_region()
            else:
                continue
        
        return x_axis, y_axis
        
        
    def prepare_df_data(self, working_df):        
        tb_name = 'xd_tb' if self.use_xd else 'tb'
        working_df = self.prepare_extra(working_df, tb_name)

        if self.isdebug:
            print("working_df: {0}".format(working_df[['chan_price', tb_name, 'real_loc','money_acc_'+tb_name, 'macd_acc_'+tb_name]]))
        return working_df
    
    def prepare_extra(self, working_df, tb_col):
        self.kbar_chan.prepare_original_kdf() # add macd term
        working_df = append_fields(
                                    working_df, 
                                    ['money_acc_'+tb_col, 'macd_acc_'+tb_col],
                                    [
                                        [0]*working_df.size,
                                        [0]*working_df.size,
                                    ],
                                    [float, float],
                                    usemask=False
                                    )
        
        original_df = self.kbar_chan.getOriginal_df()
        current_loc = 1
        previous_loc = 0
        while current_loc < working_df.size:
            current_real_loc = working_df[current_loc]['real_loc']
            previous_real_loc = working_df[previous_loc]['real_loc']
            
            # gather macd data based on real_loc, be aware of head/tail
            origin_macd = original_df[previous_real_loc+1 if previous_real_loc != 0 else None:current_real_loc+1]['macd']
            if working_df[current_loc][tb_col] == TopBotType.top.value:
                # sum all previous positive macd data 
                working_df[current_loc]['macd_acc_'+tb_col] = sum([pos_macd for pos_macd in origin_macd if pos_macd > 0])
                 
            elif working_df[current_loc][tb_col] == TopBotType.bot.value:
                # sum all previous negative macd data 
                working_df[current_loc]['macd_acc_'+tb_col] = sum([pos_macd for pos_macd in origin_macd if pos_macd < 0])
            else:
                print("Invalid {0} data".format(tb_col))
                
            # gather money data based on pivot
            origin_money = original_df[previous_real_loc+1:current_real_loc+1]['money']
            working_df[current_loc]['money_acc_'+tb_col] = sum(origin_money)
            
            previous_loc = current_loc
            current_loc = current_loc + 1

        return working_df

class Equilibrium():
    '''
    This class use ZouShi analytic results to check BeiChi
    '''
    
    def __init__(self, 
                 df_all, 
                 anal_zoushi, 
                 force_zhongshu=True, 
                 check_full_zoushi=True,
                 isdebug=False, 
                 isDescription=True):
        self.original_df = df_all
        self.analytic_result = anal_zoushi.zslx_result
        self.analytic_nodes = anal_zoushi.zslx_all_nodes
        self.isdebug = isdebug
        self.isDescription = isDescription
        self.isQvShi = False
        self.isQvShi_simple = False # used for only checking zhongshu core range
        self.isComposite = False # check full zoushi of current
        self.isExtension = False # check full zoushi of current
        self.check_full_zoushi = check_full_zoushi
        self.force_zhongshu = force_zhongshu
        self.check_zoushi_status()
        pass
    
    def find_most_recent_zoushi(self, direction, current_chan_type, enable_composite=False):
        '''
        Make sure we find the appropriate two XD for comparison.
        A. in case of QVSHI
        B. in case of no QVSHI
            1. compare the entering zhongshu XD/split XD with last XD of the zhongshu
            2. compare entering XD with exit XD for the group of complicated zhongshu
            3. compare two zslx entering and exiting zhongshu (can be opposite direction)
        '''
        if self.isQvShi:
            if current_chan_type != Chan_Type.I:
                return None, None, None, None
            if type(self.analytic_result[-1]) is ZhongShu and self.analytic_result[-1].is_complex_type():  
                zs = self.analytic_result[-1]
                first_zslx = self.analytic_result[-2]
                last_xd = zs.take_last_xd_as_zslx()
                return (first_zslx, self.analytic_result[-1], last_xd, self.analytic_result[-1].get_amplitude_region_original_without_last_xd())
            elif type(self.analytic_result[-1]) is ZouShiLeiXing:
                return (self.analytic_result[-3], self.analytic_result[-2], self.analytic_result[-1], self.analytic_result[-2].get_amplitude_region_original())
        
        else: # PANBEI
            if self.analytic_result[-1].isZhongShu:
                zs = self.analytic_result[-1]
                last_xd = zs.take_last_xd_as_zslx()
                
                if type(self.analytic_result[-1]) is CompositeZhongShu:
                    if len(self.analytic_result) > 1:
                        first_xd = self.analytic_result[-2]
                    else:
                        first_xd = zs.take_split_xd_as_zslx(direction) 
                elif zs.is_complex_type():
                    if enable_composite and len(self.analytic_result) >= 3 and\
                        type(self.analytic_result[-2]) is ZouShiLeiXing and\
                        type(self.analytic_result[-3]) is ZhongShu and\
                        self.two_zslx_interact_original(self.analytic_result[-1], self.analytic_result[-3]):
    #                     return None, None, None, None
                        # Zhongshu KUOZHAN ###############################
                        ## zhong shu combination use CompositeZhongShu class
                        i = -1
                        while -(i-2) <= len(self.analytic_result):
                            if not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i]) or\
                                (i+2 < 0 and not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i+2])):
                                break
                            i = i - 2
                        zs = CompositeZhongShu(self.analytic_result[i:], zs.original_df)
                        if -(i-1) <= len(self.analytic_result) and self.analytic_result[i-1].direction == direction:
                            first_xd = self.analytic_result[i-1]
                        else:
                            first_xd = zs.take_split_xd_as_zslx(direction)
                            
                    elif len(self.analytic_result) < 2 or self.analytic_result[-2].direction != direction:
                        first_xd = zs.take_split_xd_as_zslx(direction, contain_zs=True, force_remaining_zs=True)
                    else:
                        first_xd = self.analytic_result[-2]
                    return first_xd, zs, last_xd, zs.get_amplitude_region_original_without_last_xd()
                else:
                    # allow same direction zs
                    if zs.direction != direction:
                        return None, None, None, None
                    first_xd = zs.take_first_xd_as_zslx() if zs.direction != direction or len(self.analytic_result) < 2 else self.analytic_result[-2]
                    return first_xd, zs, last_xd, zs.get_amplitude_region_original_without_last_xd()
    
            elif type(self.analytic_result[-1]) is ZouShiLeiXing:
                last_xd = self.analytic_result[-1]
                zs = None
                if type(self.analytic_result[-2]) is CompositeZhongShu:
                    if len(self.analytic_result) > 2:
                        first_xd = self.analytic_result[-3]
                    else:
                        first_xd = zs.take_split_xd_as_zslx(direction) 
                elif enable_composite and len(self.analytic_result) >= 4 and\
                    type(self.analytic_result[-2]) is ZhongShu and\
                    type(self.analytic_result[-4]) is ZhongShu and\
                    self.two_zslx_interact_original(self.analytic_result[-4], self.analytic_result[-2]):
                    zs = self.analytic_result[-2]
                    # composite ZhongShu case ###############################
                    ## zhong shu combination
                    i = -2
                    while -(i-2) <= len(self.analytic_result):
                        if not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i]) or\
                            (i+2 < 0 and not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i+2])):
                            break
                        i = i - 2
                    zs = CompositeZhongShu(self.analytic_result[i:-1], zs.original_df)
                    if -(i-1) <= len(self.analytic_result) and self.analytic_result[i-1].direction == direction:
                        first_xd = self.analytic_result[i-1]
                    else:
                        first_xd = zs.take_split_xd_as_zslx(direction)
                        
                elif len(self.analytic_result) < 3 or self.analytic_result[-3].direction != direction:
                    if len(self.analytic_result) > 1:
                        zs = self.analytic_result[-2]
                        first_xd = zs.take_split_xd_as_zslx(direction, contain_zs=True, force_remaining_zs=True)
                    else: # no ZhongShu found
                        return None, None, None, None
                else:
                    zs = self.analytic_result[-2]
                    first_xd = self.analytic_result[-3]
                    
                # only allow same direction zs
                if zs.direction != direction:
                    return None, None, None, None
                return first_xd, zs, last_xd, zs.get_amplitude_region_original(),
                
            else:
                print("INVALID Zou Shi type")
                return None, None, None, None
    
    def standard_qvshi_check(self, zs1, zs2, zs_level=ZhongShuLevel.current):
        if zs1.get_level().value == zs2.get_level().value == zs_level.value and\
            zs1.direction == zs2.direction:
            [l1, u1] = zs1.get_amplitude_region_original()
            [l2, u2] = zs2.get_amplitude_region_original()
            if float_more(l1, u2) or float_more(l2, u1): # two Zhong Shu without intersection
                if self.isdebug:
                    print("1 current Zou Shi is QV SHI \n{0} \n{1}".format(zs1, zs2))
                return True
        return False
    
    def two_zhongshu_form_qvshi(self, zs1, zs2, all_nodes_after_zs1):
        '''
        We are only dealing with working level of QV SHI by default, and the first ZS can be higher level 
        due to the rule of connectivity:
        two adjacent ZhongShu going in the same direction, or the first ZhongShu is complex(can be both direction)
        '''
        strict_result = False
        new_zoushi = None
        if self.standard_qvshi_check(zs1, zs2):
            strict_result = True 
            
        
        # LETS NOT IGNORE COMPLEX CASES
        # complex type covers higher level type
        # if the first ZhongShu is complex and can be split to form QvShi with second ZhongShu
        # with the same structure after split as the next zhongshu
        if not strict_result and zs1.is_complex_type():
            # split first node will be the max node
            split_nodes = zs1.get_split_zs(zs2.direction, contain_zs=True) + all_nodes_after_zs1[1:]
            if len(split_nodes) >= 5:
                new_zoushi = ZouShi.analyze_api(zs2.direction, split_nodes, zs1.original_df, self.isdebug)
                new_zss = [zs for zs in new_zoushi if zs.isZhongShu]
                if len(new_zss) > 1:
                    new_zs1 = new_zss[-2]
                    new_zs2 = new_zss[-1]
                    if self.standard_qvshi_check(new_zs1, new_zs2):
                        strict_result = True 
        
        return strict_result, new_zoushi
    
    def two_zhongshu_form_qvshi_simple(self, zs1, zs2, zslx, zs_level=ZhongShuLevel.current):
        
        relax_result = False
#         if zs1.get_level().value >= zs2.get_level().value == zs_level.value:
        [lr1, ur1] = zs1.get_core_region()
        [lr2, ur2] = zs2.get_core_region()
        if (float_more(lr1, ur2) or float_more(lr2, ur1)) and\
            ((not (self.two_zslx_interact(zs1, zs2) and zslx.isSimple())) or\
            (not zs1.is_complex_type() and self.two_zslx_interact(zs1, zs2) and zslx.isSimple())): # two Zhong Shu without intersection
            if self.isdebug:
                print("1 current Zou Shi is QV SHI relaxed \n{0} \n{1}".format(zs1, zs2))
            relax_result = True
    
#         if not relax_result and zs1.get_level().value > zs2.get_level().value == zs_level.value and\
#             (zs1.direction == zs2.direction or zs1.is_complex_type()):
# #             split_nodes = zs1.get_ending_nodes(N=5)
#             split_nodes = zs1.get_split_zs(zs2.direction, contain_zs=False)
#             if len(split_nodes) >= 5 and -1<=(len(split_nodes) - 1 - (4+len(zs2.extra_nodes)))<=0:
#                 new_zs = ZhongShu(split_nodes[1], split_nodes[2], split_nodes[3], split_nodes[4], zs2.direction, zs2.original_df)
#                 new_zs.add_new_nodes(split_nodes[5:])
#      
#                 [lr1, ur1] = new_zs.get_core_region()
#                 [lr2, ur2] = zs2.get_core_region()
#                 if (float_more(lr1, ur2) or float_more(lr2, ur1)) and\
#                     (not (self.two_zslx_interact(zs1, zs2) and zslx.isSimple())): # two Zhong Shu without intersection
#                     if self.isdebug:
#                         print("2 current Zou Shi is QV SHI relaxed \n{0} \n{1}".format(new_zs, zs2))
#                     relax_result = True
        return relax_result
    
    def two_zslx_interact(self, zs1, zs2):
        result = False
        [l1, u1] = zs1.get_amplitude_region()
        [l2, u2] = zs2.get_amplitude_region()
        return (float_less_equal(l1,l2) and float_less_equal(l2, u1)) or\
                (float_less_equal(l1,u2) and float_less_equal(u2, u1)) or\
                (float_less_equal(l2,l1) and float_less_equal(l1, u2)) or\
                (float_less_equal(l2,u1) and float_less_equal(u1, u2))
    
    def two_zslx_interact_original(self, zs1, zs2):
        result = False
        [l1, u1] = zs1.get_amplitude_region_original()
        [l2, u2] = zs2.get_amplitude_region_original()
        return (float_less_equal(l1,l2) and float_less_equal(l2, u1)) or\
                (float_less_equal(l1,u2) and float_less_equal(u2, u1)) or\
                (float_less_equal(l2,l1) and float_less_equal(l1, u2)) or\
                (float_less_equal(l2,u1) and float_less_equal(u1, u2))
    
    def get_effective_time(self):
        # return the ending timestamp of current analytic result
        return self.analytic_result[-1].get_time_region()[1]
    
    def check_zoushi_status(self):
        # check if current status beichi or panzhengbeichi
        recent_zoushi = self.analytic_result
        recent_zhongshu = []
        for zs in recent_zoushi:
            if zs.isZhongShu:
                recent_zhongshu.append(zs)
        
        if len(recent_zhongshu) < 2:
            self.isQvShi = False
            if self.isdebug:
                print("less than two zhong shu")
            return
        
        # there should be at least 3 zoushi elem by now
        zoushi_idx_after_zs2 = -2 if recent_zoushi[-1].isZhongShu else -3
        all_nodes_after_zs1 = ZouShi.get_all_zoushi_nodes(recent_zoushi[zoushi_idx_after_zs2:], 
                                                          self.analytic_nodes)
        
        # QV SHI
        self.isQvShi, new_zoushi = self.two_zhongshu_form_qvshi(recent_zhongshu[-2], recent_zhongshu[-1], all_nodes_after_zs1) 
        if self.isQvShi and self.isdebug:
            print("QU SHI 1")
        
#         # simple QVSHI
#         if type(recent_zoushi[-1]) is ZouShiLeiXing:
#             self.isQvShi_simple = self.two_zhongshu_form_qvshi_simple(recent_zhongshu[-2], recent_zhongshu[-1], self.analytic_result[-3])
#         elif len(recent_zhongshu) > 2 and not recent_zhongshu[-1].is_complex_type(): # This is the case of TYPE III
#             self.isQvShi_simple = self.two_zhongshu_form_qvshi_simple(recent_zhongshu[-3], recent_zhongshu[-2], self.analytic_result[-4])
            
        
        if self.check_full_zoushi:
            # mark if curent zoushi contain ZhongShu extension or composition
            # This is needed if we need to have full picture of current zoushi, in which case we avoid them
            # e.g. sub level or bi level
            for zs in recent_zhongshu:
                if zs.get_level().value > ZhongShuLevel.current.value:
                    self.isExtension = True
                    break
            
            i = 0
            while i + 1 < len(recent_zhongshu):
                if self.two_zslx_interact(recent_zhongshu[i], recent_zhongshu[i+1]):
                    self.isComposite = True
                    break
                i += 1
            # mark if curent zoushi contain ZhongShu extension or composition
        else: # This should only happen at top level where we don't need full zoushi check
            if self.isQvShi and new_zoushi is not None:
                if self.isdebug:
                    print("Analyic results updated to suit QVSHI")
                self.analytic_result = new_zoushi
        
#         # TWO ZHONG SHU followed by ZHONGYIN ZHONGSHU
#         # first two zhong shu no interaction
#         # last zhong shu interacts with second, this is for TYPE II trade point
#         if len(recent_zhongshu) >= 3 and\
#             (recent_zhongshu[-2].direction == recent_zhongshu[-1].direction) and\
#             recent_zhongshu[-1].is_complex_type():
#             first_two_zs_qs = self.two_zhongshu_form_qvshi(recent_zhongshu[-3], recent_zhongshu[-2])
#             second_third_interact = self.two_zslx_interact_original(recent_zhongshu[-2], recent_zhongshu[-1])
#             self.isQvShi = first_two_zs_qs and second_third_interact
#             if self.isQvShi and self.isdebug:
#                 print("QU SHI 2")
#         else:
#             self.isQvShi = False

    def check_zoushi_structure(self, zoushi, at_bi_level, enable_composite=True):
        '''
        This method checks the whole zoushi structure under evaluation, make ZhongShu Composite if necessary.
        check if it's structurally balanced. 
        This is necessary in sub level for exhaustion check
        '''
        
        all_zs = [zs.isBenZouStyle() for zs in zoushi if zs.isZhongShu]
        all_zs_strong = [zs.isStrongBenZouStyle() for zs in zoushi if zs.isZhongShu]
#         all_zs = all_zs[-2:] if self.isQvShi else all_zs[-1:]
        # benzou check only for panbei
        if np.any(all_zs[-1:]) and not self.isQvShi and not at_bi_level:
            if self.isdebug:
                print("BenZou Zhongshu detected for PanBei, We can't analyze this type of zoushi")
            return False
        elif np.any(all_zs_strong[-1:]) and self.isQvShi and not at_bi_level:
            if self.isdebug:
                print("Strong BenZou Zhongshu detected for BeiChi, We can't analyze this type of zoushi")
            return False
        # TODO check zoushi structure by finding the zhongshus with the highest level. 
        # the Zoushi before and after that Zhongshu should have the same level
        if self.check_full_zoushi:
            new_zoushi = []
            if self.isComposite:
                if not enable_composite:
                    if self.isdebug:
                        print("Composite found, but we disabled it. return False")
                    return False
                # make the composite and update the zoushi
                start_idx = None
                i = -1
                while -i <= len(self.analytic_result):
                    current_zs = self.analytic_result[i]
                    if current_zs.isZhongShu:
                        if -(i-2) > len(self.analytic_result):
                            if start_idx is not None:
                                end_idx = start_idx+1
                                zs = CompositeZhongShu(self.analytic_result[i:(end_idx if end_idx!=0 else None)], current_zs.original_df)
                                new_zoushi.insert(0, zs)
                                start_idx = None
                                i = i - 1
                                continue
                        else:
                            if start_idx is not None and\
                                (
                                    not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i]) or\
                                    (i+2 < 0 and not self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i+2]))
                                ):
                                end_idx = start_idx+1
                                zs = CompositeZhongShu(self.analytic_result[i:(end_idx if end_idx!=0 else None)], current_zs.original_df)
                                new_zoushi.insert(0, zs)
                                start_idx = None
                                i = i - 1
                                continue
                            elif self.two_zslx_interact_original(self.analytic_result[i-2], self.analytic_result[i]):
                                start_idx = i if start_idx is None else start_idx
                                i = i - 2
                                continue
                    new_zoushi.insert(0, current_zs)
                    i = i - 1
            
            if not new_zoushi:
                new_zoushi = self.analytic_result
            
            # find zhongshu with highest level
            all_zs_level_value = [zs.get_level().value for zs in new_zoushi]
            max_level_value = max(all_zs_level_value)
            if max_level_value > ZhongShuLevel.current.value:
                max_level_idx = np.where(np.array(all_zs_level_value)==max_level_value)[0]
                
                if len(max_level_idx) >= 2:
                    new_zoushi = new_zoushi[max_level_idx[-2]+1:]
                    all_zs_level_value = [zs.get_level().value for zs in new_zoushi]
                    max_level_idx = np.where(np.array(all_zs_level_value)==max_level_value)[0]
                
                zoushi_1 = new_zoushi[:max_level_idx[-1]]
                zoushi_2 = new_zoushi[max_level_idx[-1]+1:]
                
                if zoushi_1 and zoushi_2:
                    zslx1 = CompositeZouShiLeiXing(zoushi_1, new_zoushi[-1].original_df)
                    zslx2 = CompositeZouShiLeiXing(zoushi_2, new_zoushi[-1].original_df)
        
        #             if self.isExtension:
        #             if self.isdebug:
        #                 print("check full zoushi, found ZhongShu composite:{0} extension:{1}".format(self.isComposite,self.isExtension))
                    exhausted, _, _ = self.two_zoushi_exhausted(zslx1, zslx2, True)
                    if not exhausted:
                        if self.isdebug:
                            print("high level ZhongShu found in Zoushi, it failed the exhaustion check")
                        return False
                    else:
                        self.analytic_result = zslx2.zslx_list
                        self.force_zhongshu = zslx2.get_level().value >= ZhongShuLevel.current.value
                        if self.isdebug:
                            print("self.analytic_result updated to zoushileixing (working level or below): {0}, force zhongshu: {1}".format(zslx2, self.force_zhongshu))
        return True
    
    def define_equilibrium(self, direction, 
                           guide_price=0, 
                           check_tb_structure=False, 
                           check_balance_structure=False, 
                           current_chan_type=Chan_Type.INVALID,
                           at_bi_level=False, # True currently at bi level
                           allow_simple_zslx=True, # allow simple zoushileixing to be true
                           enable_composite=False): # allow composite zs, currently only at bi level
        '''
        We are dealing type III differently at top level
        return:
        exhaustion
        xd_exhaustion
        zoushi start time
        sub split time
        slope
        force
        '''
        if not self.check_zoushi_structure(self.analytic_result, at_bi_level, enable_composite):
            return False, False, None, None, 0, 0
        
        # We shouldn't have III at BI level, only PB or BC
        if current_chan_type == Chan_Type.III and not at_bi_level:
#             if self.isQvShi_simple or self.isQvShi:
#                 if self.isdebug:
#                     print("type III mixed with type I position we ignore")
#                 return False, False, None, None, 0, 0
            
            last_zoushi = self.analytic_result[-1]
            if type(last_zoushi) is ZouShiLeiXing:
                split_direction, split_nodes = last_zoushi.get_reverse_split_zslx()
                pure_zslx = ZouShiLeiXing(split_direction, last_zoushi.original_df, split_nodes)
                
                xd_exhaustion, ts = pure_zslx.check_exhaustion() 
                return True, xd_exhaustion, last_zoushi.zoushi_nodes[0].time, ts, 0, 0
            else: # ZhongShu case 
                xd_exhaustion, ts = last_zoushi.check_exhaustion()
                return True, xd_exhaustion, last_zoushi.first.time, ts, 0, 0
        
        # if we only have one zhongshu / ZSLX we can only rely on the xd level check
        if len(self.analytic_result) < 2:
            if type(self.analytic_result[-1]) is ZouShiLeiXing: 
                if self.force_zhongshu:
                    if self.isdebug:
                        print("ZhongShu not yet formed, force zhongshu return False")
                    return False, False, None, None, 0, 0
                
                zslx = self.analytic_result[-1]
                if self.isdebug:
                    print("ZhongShu not yet formed, only check ZSLX exhaustion")
                xd_exhaustion, ts = zslx.check_exhaustion(allow_simple_zslx) # only used if we want to avoid one xd
                return True, xd_exhaustion, zslx.zoushi_nodes[0].time, ts, 0, 0
            elif type(self.analytic_result[-1]) is ZhongShu:
                zs = self.analytic_result[-1]
#                 if zs.get_level().value > ZhongShuLevel.current.value and not at_bi_level:
#                     if self.isdebug:
#                         print("Pan Bei Zhong Shu level too high")
#                     return False, False, zs.first.time, ts, 0, 0
                if self.isdebug:
                    print("only one zhongshu, check zhongshu exhaustion")
                xd_exhaustion, ts = zs.check_exhaustion()
                return True, xd_exhaustion, zs.first.time, ts, 0, 0
        
        a, central_B, c, central_region = self.find_most_recent_zoushi(direction, current_chan_type, enable_composite=enable_composite)
        
        new_high_low = self.reached_new_high_low(guide_price, direction, c, central_region)
        
        if self.check_equilibrium_structure(a, 
                                           central_B, 
                                           c, 
                                           direction, 
                                           check_tb_structure=check_tb_structure,
                                           check_balance_structure=check_balance_structure,
                                           current_chan_type=current_chan_type,
                                           at_bi_level=at_bi_level):
            return self.check_exhaustion(a, c, new_high_low)
        else:
            return False, False, None, None, 0, 0
    
    def check_equilibrium_structure(self, 
                               zslx_a, 
                               central_B, 
                               zslx_c, 
                               direction, 
                               check_tb_structure=False,
                               check_balance_structure=False, 
                               current_chan_type=Chan_Type.INVALID,
                               at_bi_level=False):
        if zslx_a is None or zslx_c is None or zslx_a.isEmpty() or zslx_c.isEmpty():
            if self.isdebug:
                print("Not enough DATA check_exhaustion")
            return False
        
        a_s = zslx_a.get_tb_structure() 
        c_s =zslx_c.get_tb_structure()

        a_time = zslx_a.get_time_diff()
        c_time = zslx_c.get_time_diff()
        b_time = [a_time[1], c_time[0]]
        
        a_range = zslx_a.get_amplitude_region_original()
        c_range = zslx_c.get_amplitude_region_original()
        b_range = central_B.get_core_region() # use core region
        
        if zslx_c.direction != direction:
            if self.isdebug:
                print("Invalid last XD direction: {0}".format(zslx_c.direction))
            return False
        
        price_sound = True
        if direction == TopBotType.top2bot:
            price_sound = float_more_equal(a_range[1], b_range[1]) and float_more_equal(b_range[0], c_range[0])
        elif direction == TopBotType.bot2top:
            price_sound = float_less_equal(a_range[0], b_range[0]) and float_less_equal(b_range[1], c_range[1])
        if not price_sound:
            if self.isdebug:
                print("price within ZhongShu range")
            return False
        
        # short circuit BI level avoid structural check
        if at_bi_level:
            return True
        
        if check_tb_structure:
             if a_s[0] != c_s[0] or a_s[-1] != c_s[-1]:
#            if not ((a_s[0] == c_s[0] and a_s[-1] == c_s[-1]) or\
#               (a_s[0] == TopBotType.reverse(c_s[0]) and a_s[-1] == TopBotType.reverse(c_s[-1]))):
                if self.isdebug:
                    print("Not matching tb structure")
                return False
        
        if self.isQvShi and current_chan_type==Chan_Type.I: # BEI CHI
            if abs(len(a_s) - len(c_s)) > 4:
                if self.isdebug:
                    print("Not matching XD structure")
                return False
        else: # PAN BEI #
#             if abs(len(a_s) - len(c_s)) >= 4:
            if len(a_s) != len(c_s):
                if check_balance_structure:
                    if not self.price_balance(a_range, b_range, c_range):
#                     (not self.price_balance(a_range, b_range, c_range) or\
#                      not self.time_balance(a_time, b_time, c_time)):
                        if self.isdebug:
                            print("Not matching XD balane")
                        return False
                else:
                    if self.isdebug:
                        print("Not matching XD structure")
                    return False
            
        
        return True
    
    def price_balance(self, a_range, b_range, c_range):
        balance_point = (max(a_range[1], c_range[1]) + min(a_range[0], c_range[0]))/2
        result = float_less_equal(b_range[0], balance_point) and float_less_equal(balance_point, b_range[1])
        if self.isdebug and not result:
            print("price range balance failed")
        return result

    def time_balance(self, a_time, b_time, c_time):
        balance_point = (c_time[1] + a_time[0]) / 2
        result = float_less_equal(b_time[0], balance_point) and float_less_equal(balance_point, b_time[1])
        if self.isdebug and not result:
            print("time range balance failed")
        return result
    
    def reached_new_high_low(self, guide_price, direction, zslx, central_region):
        if zslx is None or zslx.isEmpty():
            return False
        
        if guide_price == 0: # This happens at BI level
            guide_price = central_region[0] if direction == TopBotType.top2bot else central_region[1]
            
        zslx_range = zslx.get_amplitude_region_original()
        
        return float_less_equal(zslx_range[0], guide_price) if direction == TopBotType.top2bot else float_more_equal(zslx_range[1], guide_price)
    
    def two_zoushi_exhausted(self, zslx_a, zslx_c, new_high_low):
        exhaustion_result = False
        
        zslx_slope = zslx_a.work_out_slope()
        
        latest_slope = zslx_c.work_out_slope()
        if np.sign(latest_slope) == 0 or np.sign(zslx_slope) == 0:
            if self.isdebug:
                print("Invalid slope {0}, {1}".format(zslx_slope, latest_slope))
            return False, 0, 0
        
        if np.sign(latest_slope) == np.sign(zslx_slope) and float_less(abs(latest_slope), abs(zslx_slope)):
            if self.isdebug:
                print("exhaustion found by reduced slope: {0} {1}".format(zslx_slope, latest_slope))
            exhaustion_result = True

        zslx_force = 0
        zslx_macd = 0
        if not exhaustion_result and new_high_low:
            # macd is converted by mangitude as conversion factor to 
            # work out the force per unit timeprice value <=> presure
            # macd / (price * time)
            
            zslx_macd = zslx_a.work_out_macd_strength()
            latest_macd = zslx_c.work_out_macd_strength()
            exhaustion_result = float_more(abs(zslx_macd), abs(latest_macd))
            if self.isdebug:
                print("{0} found by macd: {1}, {2}".format("exhaustion" if exhaustion_result else "exhaustion not", zslx_macd, latest_macd))
            
            if not exhaustion_result:
                zslx_a_force = zslx_a.work_out_force()
                zslx_force = zslx_c.work_out_force()
                exhaustion_result = float_more(abs(zslx_a_force), abs(zslx_force))
                if self.isdebug:
                    print("{0} found by force: {1}, {2}".format("exhaustion" if exhaustion_result else "exhaustion not", zslx_a_force, zslx_force))
        return exhaustion_result, zslx_slope, zslx_force

    def check_exhaustion(self, zslx_a, zslx_c, new_high_low):
        exhaustion_result, zslx_slope, zslx_force = self.two_zoushi_exhausted(zslx_a, zslx_c, new_high_low)
        #################################################################################################################
        # try to see if there is xd level zslx exhaustion
        check_xd_exhaustion, sub_split_time = zslx_c.check_exhaustion()
        if self.isdebug:
            print("{0} found at XD level".format("exhaustion" if check_xd_exhaustion else "exhaustion not"))
        
        # We don't do precise split with sub_split_time, but give the full range! zslx_a.zoushi_nodes[0].time this is used while we go from top to sub level
        # from sub to bi level, we use precise cut therefore zslx_c.zoushi_nodes[0].time
        return exhaustion_result, check_xd_exhaustion, zslx_c.zoushi_nodes[0].time, sub_split_time, zslx_slope, zslx_force
        
    def check_chan_type(self, check_end_tb=False):
        '''
        This method determines potential TYPE of trade point under CHAN
        '''
        all_types = []
        if len(self.analytic_result) < 2 and not self.analytic_result[0].isZhongShu:
            return all_types
        
        # we can't supply the Zhongshu amplitude range as it is considered part of Zhongshu
        # SIMPLE CASE
        if self.isQvShi:
            # I current Zou Shi must end
            if type(self.analytic_result[-1]) is ZouShiLeiXing: # last zslx escape last zhong shu
                zslx = self.analytic_result[-1]
                zs = self.analytic_result[-2]
                zslx2= self.analytic_result[-3]
                [lc, uc] = zs.get_amplitude_region_original()
                if zslx.direction == zslx2.direction:
                    if zslx.direction == TopBotType.top2bot and\
                        (not check_end_tb or\
                         (zslx.zoushi_nodes[-1].tb == TopBotType.bot and\
                        float_less(zslx.zoushi_nodes[-1].chan_price, lc))):
                            if self.isdebug:
                                print("TYPE I trade point 1")
                            all_types.append((Chan_Type.I, TopBotType.top2bot, lc))
                    elif zslx.direction == TopBotType.bot2top and\
                        (not check_end_tb or\
                         (zslx.zoushi_nodes[-1].tb == TopBotType.top and\
                        float_more(zslx.zoushi_nodes[-1].chan_price, uc))):
                            if self.isdebug:
                                print("TYPE I trade point 2")
                            all_types.append((Chan_Type.I, TopBotType.bot2top, uc))
            
            if type(self.analytic_result[-1]) is ZhongShu: # last XD in zhong shu must make top or bot
                zs = self.analytic_result[-1]
                [lc, uc] = zs.get_amplitude_region_original_without_last_xd()
                if zs.is_complex_type() and len(zs.extra_nodes) >= 1:
                    if zs.direction == TopBotType.top2bot and\
                        (not check_end_tb or\
                         (zs.extra_nodes[-1].tb == TopBotType.bot and\
                        float_less(zs.extra_nodes[-1].chan_price, lc))):
                        if self.isdebug:
                            print("TYPE I trade point 3")
                        all_types.append((Chan_Type.I, TopBotType.top2bot, lc))
                    elif zs.direction == TopBotType.bot2top and\
                        (not check_end_tb or\
                         (zs.extra_nodes[-1].tb == TopBotType.top and\
                        float_more(zs.extra_nodes[-1].chan_price, uc))):
                        all_types.append((Chan_Type.I, TopBotType.bot2top, uc))
                        if self.isdebug:
                            print("TYPE I trade point 4")

#             # II Zhong Yin Zhong Shu must form
#             # case of return into last QV shi Zhong shu
#             if type(self.analytic_result[-1]) is ZhongShu: # Type I return into core region
#                 zs = self.analytic_result[-1]
#                 if zs.is_complex_type() and\
#                     len(zs.extra_nodes) >= 2:
#                     core_region = zs.get_core_region()
#                     if (zs.direction == TopBotType.bot2top and\
#                         zs.extra_nodes[-2].chan_price < core_region[1]) or\
#                         (zs.direction == TopBotType.top2bot and\
#                          zs.extra_nodes[-2].chan_price > core_region[0]):
#                             if check_end_tb:
#                                 if ((zs.extra_nodes[-1].tb == TopBotType.top and zs.direction == TopBotType.bot2top) or\
#                                     (zs.extra_nodes[-1].tb == TopBotType.bot and zs.direction == TopBotType.top2bot)):
#                                     all_types.append((Chan_Type.II, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
#                                     if self.isdebug:
#                                         print("TYPE II trade point 1")                            
#                             else:
#                                 all_types.append((Chan_Type.II, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
#                                 if self.isdebug:
#                                     print("TYPE II trade point 2")
# 
#             # case of return into last QV shi amplitude zhong yin zhongshu about to form
#             # simple case where weak III short forms.
#             if type(self.analytic_result[-1]) is ZouShiLeiXing:
#                 zs = self.analytic_result[-2]
#                 zslx = self.analytic_result[-1]
#                 if zs.direction == zslx.direction and\
#                     len(zslx.zoushi_nodes) >= 3:
#                     core_region = zs.get_core_region()
#                     amplitude_region = zs.get_amplitude_region_original()  
#                     if (zs.direction == TopBotType.bot2top and\
#                         zslx.zoushi_nodes[-3].chan_price > amplitude_region[1] and\
#                         zslx.zoushi_nodes[-2].chan_price <= amplitude_region[1] and\
#                         zslx.zoushi_nodes[-1].chan_price > amplitude_region[1]) or\
#                         (zs.direction == TopBotType.top2bot and\
#                          zslx.zoushi_nodes[-3].chan_price < amplitude_region[0] and\
#                          zslx.zoushi_nodes[-2].chan_price >= amplitude_region[0] and\
#                          zslx.zoushi_nodes[-1].chan_price < amplitude_region[0]):
#                             if check_end_tb:
#                                 if ((zslx.zoushi_nodes[-1].tb == TopBotType.top and zs.direction == TopBotType.bot2top) or\
#                                     (zslx.zoushi_nodes[-1].tb == TopBotType.bot and zs.direction == TopBotType.top2bot)):
#                                     all_types.append((Chan_Type.II_weak, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
#                                     if self.isdebug:
#                                         print("TYPE II trade point 3")                            
#                             else:
#                                 all_types.append((Chan_Type.II_weak, zs.direction, core_region[0] if zs.direction == TopBotType.top2bot else core_region[1]))
#                                 if self.isdebug:
#                                     print("TYPE II trade point 4")
                                    
        # III current Zhong Shu must end, simple case
        if type(self.analytic_result[-1]) is ZouShiLeiXing:
            zslx = self.analytic_result[-1]
            zs = self.analytic_result[-2]
            core_region = zs.get_core_region()
            amplitude_region_original = zs.get_amplitude_region_original()
            
            if len(zslx.zoushi_nodes) == 3 and\
                (float_less(zslx.zoushi_nodes[-1].chan_price, amplitude_region_original[0]) or float_more(zslx.zoushi_nodes[-1].chan_price, amplitude_region_original[1])):
                if not check_end_tb or\
                    (zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.top) or\
                   (zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.bot):
                    type_direction = TopBotType.top2bot if zslx.zoushi_nodes[-1].tb == TopBotType.bot else TopBotType.bot2top
                    
                    all_types.append((Chan_Type.III_strong if zs.get_level().value > ZhongShuLevel.current.value else Chan_Type.III, 
                                      type_direction,
                                      amplitude_region_original[1] if type_direction == TopBotType.top2bot else amplitude_region_original[0]))
                    if self.isdebug:
                        print("TYPE III trade point 1")
                        
            elif len(zslx.zoushi_nodes) == 3 and\
                (float_less(zslx.zoushi_nodes[-1].chan_price, core_region[0]) or float_more(zslx.zoushi_nodes[-1].chan_price, core_region[1])):
                if not check_end_tb or\
                    (zslx.direction == TopBotType.top2bot and zslx.zoushi_nodes[-1].tb == TopBotType.top) or\
                   (zslx.direction == TopBotType.bot2top and zslx.zoushi_nodes[-1].tb == TopBotType.bot):                
                    type_direction = TopBotType.top2bot if zslx.zoushi_nodes[-1].tb == TopBotType.bot else TopBotType.bot2top
                    all_types.append((Chan_Type.III_strong if zs.get_level().value > ZhongShuLevel.current.value else Chan_Type.III_weak,
                                      type_direction,
                                      core_region[1] if type_direction == TopBotType.top2bot else core_region[0]))
                    if self.isdebug:
                        print("TYPE III trade point 2")
            
            # a bit more complex type than standard two XD away and not back case, no new zs formed   
            if len(zslx.zoushi_nodes) > 3:
                split_direction, split_nodes = zslx.get_reverse_split_zslx()
                pure_zslx = ZouShiLeiXing(split_direction, self.original_df, split_nodes)
                
                # at least two split nodes required to form a zslx
                if len(split_nodes) >= 2 and not self.two_zslx_interact_original(zs, pure_zslx):
                    if not check_end_tb or\
                    ((pure_zslx.direction == TopBotType.top2bot and pure_zslx.zoushi_nodes[-1].tb == TopBotType.bot) or\
                    (pure_zslx.direction == TopBotType.bot2top and pure_zslx.zoushi_nodes[-1].tb == TopBotType.top)):
                        all_types.append((Chan_Type.III_strong if zs.get_level().value > ZhongShuLevel.current.value else Chan_Type.III,
                                          pure_zslx.direction,
                                          amplitude_region_original[1] if pure_zslx.direction == TopBotType.top2bot else amplitude_region_original[0]))
                        if self.isdebug:
                            print("TYPE III trade point 7")
                elif len(split_nodes) >= 2 and\
                    (float_less(pure_zslx.zoushi_nodes[-1].chan_price, core_region[0]) or float_more(zslx.zoushi_nodes[-1].chan_price, core_region[1])):
                    if not check_end_tb or\
                    ((pure_zslx.direction == TopBotType.top2bot and pure_zslx.zoushi_nodes[-1].tb == TopBotType.bot) or\
                    (pure_zslx.direction == TopBotType.bot2top and pure_zslx.zoushi_nodes[-1].tb == TopBotType.top)):
                        all_types.append((Chan_Type.III_strong if zs.get_level().value > ZhongShuLevel.current.value else Chan_Type.III_weak,
                                          pure_zslx.direction,
                                          core_region[1] if pure_zslx.direction == TopBotType.top2bot else core_region[0]))
                        if self.isdebug:
                            print("TYPE III trade point 8")
        
        # We do check panbei if it's Zhongshu this case is not considered as TYPE III
        # TYPE III where zslx form reverse direction zhongshu, and last XD of new zhong shu didn't go back 
#         if len(self.analytic_result) >= 3 and type(self.analytic_result[-1]) is ZhongShu:
#             pre_zs = self.analytic_result[-3]
#             zslx = self.analytic_result[-2]
#             now_zs = self.analytic_result[-1]
#             core_region = pre_zs.get_core_region()
#             amplitude_region_original = pre_zs.get_amplitude_region_original()
#             if not now_zs.is_complex_type():
#                 if not check_end_tb or\
#                 ((now_zs.forth.tb == TopBotType.bot and now_zs.direction == TopBotType.bot2top) or\
#                  (now_zs.forth.tb == TopBotType.top and now_zs.direction == TopBotType.top2bot)): # reverse type here
#                     if not self.two_zslx_interact_original(pre_zs, now_zs):
#                         all_types.append((Chan_Type.III, 
#                                           TopBotType.top2bot if now_zs.direction == TopBotType.bot2top else TopBotType.bot2top,
#                                           amplitude_region_original[1] if now_zs.direction == TopBotType.bot2top else amplitude_region_original[0]))
#                         if self.isdebug:
#                             print("TYPE III trade point 3")
#                     elif not self.two_zslx_interact(pre_zs, now_zs):
#                         all_types.append((Chan_Type.III_weak, 
#                                           TopBotType.top2bot if now_zs.direction == TopBotType.bot2top else TopBotType.bot2top,
#                                           core_region[1] if now_zs.direction == TopBotType.bot2top else core_region[0]))
#                         if self.isdebug:
#                             print("TYPE III trade point 4")
                
        # IGNORE THIS CASE!! WE NEED CERTAINTY
        # TYPE III two reverse direction zslx, with new reverse direction zhongshu in the middle
#         if len(self.analytic_result) >= 4 and type(self.analytic_result[-1]) is ZouShiLeiXing:
#             latest_zslx = self.analytic_result[-1]
#             now_zs = self.analytic_result[-2]
#             pre_zs = self.analytic_result[-4]
#             amplitude_region_original = pre_zs.get_amplitude_region_original()
#             core_region = pre_zs.get_core_region()
#             if not self.two_zslx_interact_original(pre_zs, latest_zslx) and\
#                 latest_zslx.direction != now_zs.direction and\
#                 not now_zs.is_complex_type():
#                 if not check_end_tb or\
#                 ((latest_zslx.zoushi_nodes[-1].tb == TopBotType.top and latest_zslx.direction == TopBotType.bot2top) or\
#                  (latest_zslx.zoushi_nodes[-1].tb == TopBotType.bot and latest_zslx.direction == TopBotType.top2bot)):
#                     all_types.append((Chan_Type.III, 
#                                       latest_zslx.direction,
#                                       amplitude_region_original[1] if latest_zslx.direction == TopBotType.top2bot else amplitude_region_original[0]))
#                     if self.isdebug:
#                         print("TYPE III trade point 5")
#             if not self.two_zslx_interact(pre_zs, latest_zslx) and\
#                 latest_zslx.direction != now_zs.direction and\
#                 not now_zs.is_complex_type():
#                 if not check_end_tb or\
#                 ((latest_zslx.zoushi_nodes[-1].tb == TopBotType.top and latest_zslx.direction == TopBotType.bot2top) or\
#                  (latest_zslx.zoushi_nodes[-1].tb == TopBotType.bot and latest_zslx.direction == TopBotType.top2bot)):            
#                     all_types.append((Chan_Type.III_weak, 
#                                       latest_zslx.direction,
#                                       core_region[1] if latest_zslx.direction == TopBotType.top2bot else core_region[0]))
#                     if self.isdebug:
#                         print("TYPE III trade point 6")
        all_types = list(set(all_types))
        
        if not all_types: # if not found, we give the boundary of latest ZhongShu
            if type(self.analytic_result[-1]) is ZhongShu:
                final_zs = self.analytic_result[-1]
                all_types.append((Chan_Type.INVALID,
                                  TopBotType.noTopBot,
                                  final_zs.get_amplitude_region_original_without_last_xd()))
            elif len(self.analytic_result) > 1 and type(self.analytic_result[-2]) is ZhongShu:
                final_zs = self.analytic_result[-2]
                all_types.append((Chan_Type.INVALID,
                                  TopBotType.noTopBot,
                                  final_zs.get_amplitude_region_original()))
        
        if all_types and self.isdebug:
            print("all chan types found: {0}".format(all_types))
        return all_types
    
    
class NestedInterval():            
    '''
    This class utilize BEI CHI and apply them to multiple nested levels, 
    existing level goes:
    current_level -> XD -> BI
    periods goes from high to low level
    '''
    def __init__(self, 
                 stock, 
                 end_dt, 
                 periods, 
                 count=2000, 
                 isdebug=False, 
                 isDescription=True, 
                 isAnal=True, 
                 initial_pe_prep=None, 
                 initial_split_time=None,
                 initial_direction=TopBotType.noTopBot,
                 use_xd=True):
        self.stock = stock
        self.end_dt = end_dt
        self.periods = periods
        self.count = count
        self.is_anal = isAnal
        self.use_xd = use_xd # if False, can only be used for BI level check
        self.isdebug = isdebug
        self.isDescription = isDescription

        self.df_zoushi_tuple_list = {}
        
        self.prepare_data(period=initial_pe_prep, start_time=initial_split_time, initial_direction=initial_direction)
    
    def prepare_data(self, period=None, start_time=None, initial_direction=TopBotType.noTopBot):
        '''
        start_time and initial_direction can only be filled at Sub level together
        '''
        
        for pe in self.periods:
            if period is not None and pe != period:
                continue
            
            stock_df = get_bars(self.stock, 
                                 count=self.count, 
                                 end_dt=self.end_dt, 
                                 unit=pe,
                                 fields= ['date','high', 'low','close', 'money'],
                                 fq_ref_date=datetime.datetime.strptime(self.end_dt, "%Y-%m-%d %H:%M:%S") if type(self.end_dt) is str else self.end_dt,
                                 df=False) if start_time is None else\
                        get_bars_new(self.stock, 
                                 start_dt=start_time, 
                                 end_dt=self.end_dt, 
                                 unit=pe,
                                 fields= ['date','high', 'low','close', 'money'],
                                 fq_ref_date=datetime.datetime.strptime(self.end_dt, "%Y-%m-%d %H:%M:%S") if type(self.end_dt) is str else self.end_dt,
                                 df=False)
                
            kb_chan = KBarChan(stock_df, isdebug=self.isdebug)
            iis = TopBotType.top if initial_direction == TopBotType.top2bot else TopBotType.bot if initial_direction == TopBotType.bot2top else TopBotType.noTopBot
            xd_df = kb_chan.getFenDuan(initial_state=iis) if self.use_xd else kb_chan.getFenBi(initial_state=iis)
            if xd_df.size==0:
                self.df_zoushi_tuple_list[pe]=(kb_chan,None)
            else:
                crp_df = CentralRegionProcess(xd_df, kb_chan, isdebug=self.isdebug, use_xd=self.use_xd)
                anal_zoushi = crp_df.define_central_region(initial_direction=initial_direction)
                self.df_zoushi_tuple_list[pe]=(kb_chan,anal_zoushi)
    
    def completed_zhongshu(self):
        '''
        This method returns True if current zoushi contain at least one Zhongshu, we assume only one period is processed
        '''
        # high level
        _, anal_zoushi = self.df_zoushi_tuple_list[self.periods[0]]
        if anal_zoushi is None:
            return False
        zoushi_r = anal_zoushi.zslx_result
        if len(zoushi_r) >= 2:
            return True
        elif isinstance(zoushi_r[-1], ZhongShu):
            return True
        return False
    
    def analyze_zoushi(self, 
                       direction, 
                       chan_type = Chan_Type.INVALID, 
                       check_end_tb=False, 
                       check_tb_structure=False,
                       check_full_zoushi=False, 
                       enable_composite=False):
        ''' THIS METHOD SHOULD ONLY BE USED FOR TOP LEVEL!!
        This is due to the fact that at high level we can't be very precise
        1. check high level chan type
        return value: 
        a. high level exhaustion
        b. XD level exhaustion
        c. top level chan types
        d. split time 
        [(chan_t, chan_d, chan_p, high_slope, high_macd, last_zs_time, effective_time)]
        '''
        
        if self.isdebug:
            print("looking for {0} at top level {1} point with type:{2}".format("long" if direction == TopBotType.top2bot else "short",
                                                                      self.periods[0],
                                                                      chan_type))
        # high level
        kb_chan, anal_zoushi = self.df_zoushi_tuple_list[self.periods[0]]
        if anal_zoushi is None:
            return False, False, []
        eq = Equilibrium(kb_chan.getOriginal_df(), 
                         anal_zoushi, 
                         force_zhongshu=False,
                         isdebug=self.isdebug, 
                         isDescription=self.isDescription,
                         check_full_zoushi=check_full_zoushi)
        chan_types = eq.check_chan_type(check_end_tb=check_end_tb)
        if not chan_types:
            return False, False, []
        for chan_t, chan_d, chan_p in chan_types: # early checks if we have any types found with opposite direction, no need to go further
            if chan_d == TopBotType.reverse(direction):
                if self.isdebug:
                    print("opposite direction chan type found")
                return False, False, [(chan_t, chan_d, chan_p, 0, 0, None, None)]
        
        chan_t, chan_d, chan_p = chan_types[0]
        chan_type_check = (chan_t in chan_type) if (type(chan_type) is list) else (chan_t == chan_type)
        
        guide_price = (chan_p[0] if direction == TopBotType.top2bot else chan_p[1]) if type(chan_p) is list else chan_p
        
        if chan_type_check:
            high_exhausted, check_xd_exhaustion, last_zs_time, sub_split_time, high_slope, high_macd = eq.define_equilibrium(direction, 
                                                                                                    guide_price,
                                                                                                    check_tb_structure=check_tb_structure, 
                                                                                                    check_balance_structure=True,
                                                                                                    current_chan_type=chan_t,
                                                                                                    at_bi_level=False,
                                                                                                    allow_simple_zslx=True, 
                                                                                                    enable_composite=enable_composite)
            if self.isDescription or self.isdebug:
                print("Top level {0} {1} {2} {3} {4} with price level: {5}".format(self.periods[0], 
                                                                           chan_d, 
                                                                           chan_t,
                                                                           "exhausted" if high_exhausted else "continue",
                                                                           "xd exhausted" if check_xd_exhaustion else "xd continue",
                                                                           chan_p))
            return high_exhausted, check_xd_exhaustion, [(chan_t, 
                                                          chan_d, 
                                                          chan_p, 
                                                          high_slope, 
                                                          high_macd, 
                                                          last_zs_time, 
                                                          sub_split_time)]
        else:
            high_exhausted, check_xd_exhaustion = False, False
            if self.isDescription or self.isdebug:
                print("chan type check failed expected {0}, found {1}".format(chan_type, chan_types))
            
        return high_exhausted, check_xd_exhaustion, [(chan_t, chan_d, chan_p, 0, 0, None, None)]

#        We don't need thi manual split
#         split_time = anal_zoushi.sub_zoushi_time(chan_t, chan_d, check_xd_exhaustion)
#         if self.isdebug:
#             print("split time at {0}".format(split_time))

    
    def indepth_analyze_zoushi(self, 
                               direction, 
                               split_time, 
                               period, 
                               return_effective_time=False, 
                               force_zhongshu=False,
                               check_full_zoushi=True,
                               ignore_bi_xd=True):
        '''
        specifically used to gauge the smallest level of precision, check at BI level
        split_time param once provided meaning we need to split zoushi otherwise split done at data level
        this split_by_time method should only be used HERE
        force_zhongshu make sure underlining zoushi contain at least one ZhongShu
        '''
        if self.use_xd:
            kb_chan, anal_zoushi_xd = self.df_zoushi_tuple_list[period]
            
            if anal_zoushi_xd is None:
                return False, False, None, []
            
            if self.isdebug:
                print("XD split time at:{0}".format(split_time))
            
            fenbi_df = kb_chan.getFenBI_df()
            split_time_loc = np.where(fenbi_df['date']>=split_time)[0][0]
            crp_df = CentralRegionProcess(fenbi_df[split_time_loc:], kb_chan, isdebug=self.isdebug, use_xd=False)
            anal_zoushi_bi = crp_df.define_central_region(direction)
            if anal_zoushi_bi is None:
                return False, False, None, []
            
#             split_anal_zoushi_bi_result = anal_zoushi_bi.zslx_result
        else:
            kb_chan, anal_zoushi_bi = self.df_zoushi_tuple_list[period]
            if anal_zoushi_bi is None:
                return False, False, None, []
#             split_anal_zoushi_bi_result = anal_zoushi_bi.zslx_result
        
        eq = Equilibrium(kb_chan.getOriginal_df(), 
                         anal_zoushi_bi, 
                         isdebug=self.isdebug, 
                         isDescription=self.isDescription,
                         check_full_zoushi=check_full_zoushi,
                         force_zhongshu=force_zhongshu)
        all_types = eq.check_chan_type(check_end_tb=False)
        if not all_types:
            all_types = [(Chan_Type.INVALID, TopBotType.noTopBot, 0)]
        
        bi_exhausted, bi_check_exhaustion, _,bi_split_time, _, _ = eq.define_equilibrium(direction, 
                                                                                         check_tb_structure=True,
                                                                                         check_balance_structure=False,
                                                                                         current_chan_type=all_types[0][0],
                                                                                         at_bi_level=True,
                                                                                         allow_simple_zslx=True,
                                                                                         enable_composite=False)
        if (self.isdebug):
            print("BI level {0}, {1}".format(bi_exhausted, bi_check_exhaustion))
        
        return bi_exhausted, ignore_bi_xd or bi_check_exhaustion, (eq.get_effective_time() if return_effective_time else bi_split_time), all_types

    def full_check_zoushi(self, period, direction, 
                          chan_types=[Chan_Type.INVALID, Chan_Type.I],
                          check_end_tb=False, 
                          check_tb_structure=False,
                          force_zhongshu=False,
                          allow_simple_zslx=True,
                          check_full_zoushi=True,
                          ignore_sub_xd=False):
        '''
        split done at data level
        
        return working level:
        a working level exhaustion
        b xd level exhaustion
        c chan type/price level
        d split time
        e effective time
        '''
        if self.isdebug:
            print("looking for {0} at top level {1}".format("long" if direction == TopBotType.top2bot else "short",
                                                            period))
        kb_chan, anal_zoushi = self.df_zoushi_tuple_list[period]
        default_chan_type_result = [(Chan_Type.INVALID, TopBotType.noTopBot, 0, 0, 0, None, None)]# default value
        if anal_zoushi is None:
            return False, False, default_chan_type_result
        
        eq = Equilibrium(kb_chan.getOriginal_df(), 
                         anal_zoushi, 
                         isdebug=self.isdebug, 
                         isDescription=self.isDescription,
                         force_zhongshu=force_zhongshu, 
                         check_full_zoushi=check_full_zoushi)
        chan_type_result = eq.check_chan_type(check_end_tb=check_end_tb)
        if not chan_type_result:
            chan_type_result = [(Chan_Type.INVALID, TopBotType.noTopBot, 0)]
        
        found_chan_type = False
        for chan_t, chan_d, _ in chan_type_result: # early checks if we have any types found with opposite direction, no need to go further
            if chan_d == TopBotType.reverse(direction):
                if self.isdebug:
                    print("opposite direction chan type found")
                return False, False, default_chan_type_result
            
            if chan_t in chan_types:
                found_chan_type = True
        
        if not found_chan_type:
            if self.isdebug:
                print("chan type {0} not found".format(chan_type_result))
            return False, False, default_chan_type_result

        # only type II and III can coexist, only need to check the first one
        # reverse direction case are dealt above
        chan_t, chan_d, chan_p = chan_type_result[0]
        guide_price = (chan_p[0] if direction == TopBotType.top2bot else chan_p[1]) if type(chan_p) is list else chan_p
        exhausted, check_xd_exhaustion, sub_start_time, sub_split_time, a_slope, a_macd = eq.define_equilibrium(direction, 
                                                                                                   guide_price, 
                                                                                                   check_tb_structure=check_tb_structure,
                                                                                                   check_balance_structure=False,
                                                                                                   current_chan_type=chan_t,
                                                                                                   at_bi_level=False,
                                                                                                   allow_simple_zslx=allow_simple_zslx,
                                                                                                   enable_composite=False)
        if self.isDescription or self.isdebug:
            print("working level {0} {1} {2} {3} {4} with price:{5}".format(period, 
                                                                        chan_d, 
                                                                        "exhausted" if exhausted else "continue",
                                                                        "xd exhausted" if check_xd_exhaustion else "xd continues",
                                                                        chan_t,
                                                                        chan_p))
        return exhausted, check_xd_exhaustion, [(chan_t, 
                                                 chan_d, 
                                                 chan_p, 
                                                 a_slope, 
                                                 a_macd, 
                                                 sub_start_time if ignore_sub_xd else sub_split_time, 
                                                 eq.get_effective_time())] 
