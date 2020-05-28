# -*- encoding: utf8 -*-
'''
Created on 23 Dec 2019

@author: MetalInvest
'''

import numpy as np
import pandas as pd
import talib
from collections import OrderedDict
from biaoLiStatus import * 
from kBar_Chan import *

from chan_common_include import ZhongShuLevel, Chan_Type

def take_start_price(elem):
    if len(elem.zoushi_nodes) > 0:
        return elem.zoushi_nodes[-1].chan_price
    else:
        return 0
    
def slope_calculation(first_elem, second_elem):
    off_set = second_elem.loc - first_elem.loc
    if np.isclose(off_set, 0.0):
        print("0 offset, INVALID")
        return 0
    return 100 * (second_elem.chan_price - first_elem.chan_price) / first_elem.chan_price / off_set

class Chan_Node(object):
    def __init__(self, df_node):
        self.time = df_node['date']
        self.chan_price = df_node['chan_price']
        self.loc = df_node['real_loc']
    
    def __repr__(self):
        return "price: {0} time: {1} loc: {2} ".format(self.chan_price, self.time, self.loc)
    
    def __eq__(self, node):
        return self.time == node.time and self.chan_price == node.chan_price and self.loc == node.loc

class XianDuan_Node(Chan_Node):
    def __init__(self, df_node):
        super(XianDuan_Node, self).__init__(df_node)
        self.tb = TopBotType.value2type(df_node['xd_tb'])
        self.macd_acc = df_node['macd_acc_xd_tb']
        self.money_acc = df_node['money_acc_xd_tb'] / 1e8
        
    def __repr__(self):
        return super().__repr__() + "tb: {0}".format(self.tb)
    
    def __eq__(self, node):
        return super().__eq__(node) and self.tb == node.tb
    
    def __hash__(self):
        return hash((self.time, self.chan_price, self.loc, self.tb.value))
        
class BI_Node(Chan_Node):
    def __init__(self, df_node):
        super(BI_Node, self).__init__(df_node)
        self.tb = TopBotType.value2type(df_node['tb'])
        self.macd_acc = df_node['macd_acc_tb']
        self.money_acc = df_node['money_acc_tb'] / 1e8

    def __repr__(self):
        return super().__repr__() + "tb: {0}".format(self.tb)
    
    def __eq__(self, node):
        return super().__eq__(node) and self.tb == node.tb
    
    def __hash__(self):
        return hash((self.time, self.chan_price, self.loc, self.tb.value))

class Double_Nodes(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end
        assert isinstance(self.start, (Chan_Node, XianDuan_Node, BI_Node)), "Invalid starting node type"
        assert isinstance(self.end, (Chan_Node, XianDuan_Node, BI_Node)), "Invalid ending node type"
        assert (start.tb == TopBotType.top and end.tb == TopBotType.bot) or (start.tb == TopBotType.bot and end.tb == TopBotType.top), "Invalid tb info" 
        assert (start.time < end.time), "Invalid node timing order"
        self.direction = TopBotType.bot2top if self.start.chan_price < self.end.chan_price else TopBotType.top2bot

    def get_time_region(self):
#         # first node timestamp loc + 1, since first node connect backwords
#         real_start_time = self.original_df.index[self.original_df.index.get_loc(self.start.time)+1]
        return self.start.time, self.end.time

    def get_price_delta(self):
        return (self.end.chan_price - self.start.chan_price) / self.start.chan_price
    
    def get_loc_diff(self):
        return (self.end.loc - self.start.loc) / 1200 * 100 # use similar conversion factor

    def work_out_magnitude(self):
        price_delta = self.get_price_delta()
        time_delta = self.get_loc_diff()
        return price_delta * time_delta

    def work_out_slope(self):
#         return 100 * (self.end.chan_price - self.start.chan_price) / self.start.chan_price / (self.end.loc - self.start.loc)
        return slope_calculation(self.start, self.end)
    
    def work_out_force(self):
        price_delta = self.get_price_delta()
        time_delta = self.get_loc_diff()
        return self.end.money_acc * price_delta / (time_delta ** 2)
    
    def work_out_macd_strength(self):
        macd_acc = self.end.macd_acc
        time_delta = self.get_loc_diff()
#         mag = self.work_out_magnitude()
#         return macd_acc / mag
        return macd_acc / time_delta

class XianDuan(Double_Nodes):
    '''
    This class takes two xd nodes 
    '''
    def __init__(self, start, end):
        Double_Nodes.__init__(self, start, end)
    
    
class BI(Double_Nodes):
    '''
    This class takes two bi nodes 
    '''
    def __init__(self, start, end):
        Double_Nodes.__init__(self, start, end)
        



class ZouShiLeiXing(object):
    '''
    ZouShiLeiXing base class, it contain a list of nodes which represents the zou shi lei xing. 
    A central region
    B normal zou shi
    '''
    def __init__(self, direction, original_df, nodes=None):
        self.original_df = original_df
        self.zoushi_nodes = nodes
        self.direction = direction
        
        self.amplitude_region = []
        self.amplitude_region_origin = []
        self.time_region = []
        self.isZhongShu = False
    
    def get_level(self):
        return ZhongShuLevel.previous
    
    def isEmpty(self):
        return not bool(self.zoushi_nodes)
    
    def isSimple(self):
        return len(self.zoushi_nodes) == 2
    
    def add_new_nodes(self, tb_nodes):
        added = False
        if type(tb_nodes) is list:
            self.zoushi_nodes = list(OrderedDict.fromkeys(self.zoushi_nodes + tb_nodes))
            added = True
#             self.zoushi_nodes = self.zoushi_nodes + tb_nodes
        else:
            if tb_nodes not in self.zoushi_nodes:
                self.zoushi_nodes.append(tb_nodes)
                added = True
        
        self.get_amplitude_region(re_evaluate=added)
        self.get_amplitude_region_original(re_evaluate=added)
        self.get_time_region(re_evaluate=added)
    
    def __repr__(self):
        if self.isEmpty():
            return "Empty Zou Shi Lei Xing!"
        [s, e] = self.get_time_region()
        return "\nZou Shi Lei Xing: {0} {1}->{2}\n[\n".format(self.direction, s, e) + '\n'.join([node.__repr__() for node in self.zoushi_nodes]) + '\n]'

    def get_all_nodes(self):
        return self.zoushi_nodes
    
    def reverse_nodes(self):
        # method used for reversal analytics
#         self.zoushi_nodes = self.zoushi_nodes[::-1]
        pass

    @classmethod
    def is_valid_central_region(cls, direction, first, second, third, forth):
        valid = False
        if direction == TopBotType.top2bot:
            valid = float_less(first.chan_price, second.chan_price) and float_more(second.chan_price, third.chan_price) and float_less(third.chan_price, forth.chan_price) and float_less_equal(first.chan_price, forth.chan_price)
        elif direction == TopBotType.bot2top:
            valid = float_more(first.chan_price, second.chan_price) and float_less(second.chan_price, third.chan_price) and float_more(third.chan_price, forth.chan_price) and float_more_equal(first.chan_price, forth.chan_price)           
        else:
            print("Invalid direction: {0}".format(direction))
        return valid

    def get_reverse_split_zslx(self):
        '''
        split current zslx by top or bot
        '''
        all_price = [node.chan_price for node in self.zoushi_nodes]
        toporbotprice = max(all_price) if self.direction == TopBotType.bot2top else min(all_price)
        return TopBotType.top2bot if self.direction == TopBotType.bot2top else TopBotType.bot2top, self.zoushi_nodes[all_price.index(toporbotprice):]
    
    def take_last_xd_as_zslx(self):
        xd = XianDuan(self.zoushi_nodes[-2], self.zoushi_nodes[-1])
        return ZouShiLeiXing(xd.direction, self.original_df, self.zoushi_nodes[-2:])

    def get_amplitude_region(self, re_evaluate=False):
        if not self.amplitude_region or re_evaluate:
            chan_price_list = [node.chan_price for node in self.zoushi_nodes]
            self.amplitude_region = [min(chan_price_list), max(chan_price_list)]
        return self.amplitude_region
    
    def get_amplitude_region_original(self, re_evaluate=False):
        if len(self.zoushi_nodes) < 2:
            return [None, None]
        
        if not self.amplitude_region_origin or re_evaluate:
            [s, e] = self.get_time_diff(re_evaluate)
            price_series = self.original_df[s:e+1][['high', 'low']]
            self.amplitude_region_origin = [price_series['low'].min(), price_series['high'].max()]
        return self.amplitude_region_origin

    def get_time_region(self, re_evaluate=False):    
        if len(self.zoushi_nodes) < 2:
            return [None, None]
        if not self.time_region or re_evaluate: # assume node stored in time order
            self.zoushi_nodes.sort(key=lambda x: x.time)
            
            # first node timestamp loc + 1, since first node connect backwords
            real_start_time = self.original_df[self.zoushi_nodes[0].loc+1]['date']
            self.time_region = [real_start_time, self.zoushi_nodes[-1].time]
        return self.time_region
    
    def get_amplitude_loc(self):
        all_node_price = [node.chan_price for node in self.zoushi_nodes]
        min_price_loc = self.zoushi_nodes[all_node_price.index(min(all_node_price))].loc
        max_price_loc = self.zoushi_nodes[all_node_price.index(max(all_node_price))].loc
        return min_price_loc, max_price_loc
    
    def get_first_node_by_direction(self, direction):
        all_nodes = self.get_all_nodes()
        
        if direction == TopBotType.top2bot:
            if all_nodes[0].tb == TopBotType.top:
                return all_nodes[0]
            else:
                return all_nodes[1]
        elif direction == TopBotType.bot2top:
            if all_nodes[0].tb == TopBotType.bot:
                return all_nodes[0]
            else:
                return all_nodes[1]
        
    def get_last_node_by_direction(self, direction):
        all_nodes = self.get_all_nodes()
        if direction == TopBotType.top2bot:
            if all_nodes[-1].tb == TopBotType.bot:
                return all_nodes[-1]
            else:
                return all_nodes[-2]
        elif direction == TopBotType.bot2top:
            if all_nodes[-1].tb == TopBotType.top:
                return all_nodes[-1]
            else:
                return all_nodes[-2]
            
            
    def work_out_slope(self):
        '''
        negative slope meaning price going down
        '''
        if not self.zoushi_nodes or len(self.zoushi_nodes) < 2:
            print("Empty zslx")
            return 0
#         min_price_loc, max_price_loc = self.get_amplitude_loc()
#         off_set = max_price_loc - min_price_loc # this could be negative
#         if np.isclose(off_set, 0.0):
#             print("0 offset, INVALID")
#             return 0
#         
#         [min_price, max_price] = self.get_amplitude_region()
#         delta = 100 * (((max_price - min_price) / max_price) if self.direction == TopBotType.top2bot else ((max_price-min_price) / min_price))
            
        first_elem = self.get_first_node_by_direction(self.direction)
        last_elem = self.get_last_node_by_direction(self.direction)

#         off_set = last_elem.loc - first_elem.loc 
#         if np.isclose(off_set, 0.0):
#             print("0 offset, INVALID")
#             return 0
#         
#         delta = 100 * (last_elem.chan_price - first_elem.chan_price) / first_elem.chan_price
#                 
#         return delta / off_set
        return slope_calculation(first_elem, last_elem)
    
    def work_out_force(self):
        '''
        work out force by formulae
        '''
        money = self.get_money_acc()
        price_delta = self.get_price_delta()
        time_delta = self.get_loc_diff()
        
        return money * price_delta / (time_delta ** 2)
    
    def work_out_macd_strength(self):
#         return self.get_macd_acc() / self.get_magnitude()
        return self.get_macd_acc() / self.get_loc_diff()
    
    def get_macd_acc(self):
        top_nodes = [node for node in self.zoushi_nodes if node.tb == TopBotType.top]
        bot_nodes = [node for node in self.zoushi_nodes if node.tb == TopBotType.bot]
        macd_acc = 0.0
        if self.direction == TopBotType.bot2top:
            macd_acc = sum([node.macd_acc for node in top_nodes])
        elif self.direction == TopBotType.top2bot:
            macd_acc = sum([node.macd_acc for node in bot_nodes])
        else:
            print("We have invalid direction for ZhongShu")
        return macd_acc
    
    def get_money_acc(self):
        # avoid taking the first node
        all_nodes = self.get_all_nodes()
        return sum([node.money_acc for node in all_nodes[1:]])
    
    def get_tb_structure(self):
        return [node.tb for node in self.zoushi_nodes]
    
    def get_time_diff(self, re_evaludate=False):
        return [min(self.zoushi_nodes[0].loc, self.zoushi_nodes[-1].loc), 
                max(self.zoushi_nodes[0].loc, self.zoushi_nodes[-1].loc)]
    
    def get_loc_diff(self):
        mag = 1200 # THSI IS AN ESTIMATE! we have to upgrade one level so 240 * 5
#         # this is only hacking method it will limit use case upto 30m
#         time_gap = self.original_df['date'][-1] - self.original_df['date'][-2]
#         if time_gap.seconds == 60: # 1m case compared at 5m
#             mag = 240 #4 * 60 # number of 1m in a trading day
#         elif time_gap.seconds == 5 * 60: # 5m case compared at 30m
#             mag = 240 #5 * 4 * 60 / 5 # number of 5m in a trading week
#         elif time_gap.seconds == 30 * 60: 
#             mag = 160 #20 * 4 * 60 / 30 # number of 30m in a trading month
#         else: # complex case # check further
#             time_gap = self.original_df['date'][-2] - self.original_df['date'][-3]
#             if time_gap.seconds == 60: # 1m case    
#                 mag = 240 #4 * 60 # number of 1m in a trading day
#             elif time_gap.seconds == 5 * 60: # 5m case
#                 mag = 240 #5 * 4 * 60 / 5 # number of 5m in a trading week
#             elif time_gap.seconds == 30 * 60: # 30m case
#                 mag = 160 #20 * 4 * 60 / 30 # number of 30m in a trading month
#             else:
#                 print("WE are working on unexpected time period!")
        
        return (self.zoushi_nodes[-1].loc - self.zoushi_nodes[0].loc) / mag * 100
    
    def get_price_delta(self):
#         [l, u] = self.get_amplitude_region_original()
#         if self.direction == TopBotType.top2bot:
#             delta = (u-l)/u * 100.0
#         else:
#             delta = (u-l)/l * 100.0
            
        first_p = self.zoushi_nodes[0].chan_price
        second_p = self.zoushi_nodes[-1].chan_price
        delta = (second_p - first_p) / first_p
        return delta
    
    def get_magnitude(self): 
        # by our finding of dynamic equilibrium, the magnitude (SHIJIA) is defined as 
        # (delta time ** 2 + delta price ** 2) ** 0.5
        # delta time is based off per trading day month roughly 20 days
        # delta price is based on increase/decrease by % value
        # magnitude is defined using ln same magnitude 
        delta = self.get_price_delta()
        loc_diff = self.get_loc_diff()
#         return loc_diff ** 2 / delta
        return delta * loc_diff
#         return (delta**2 + loc_diff**2) ** 0.5
    
    def check_exhaustion(self, allow_simple_zslx=True):
        '''
        check most recent two XD or BI at current direction on slopes
        check if current ZSLX or series of ZSLX are exhausted.
        return bool value, and the split timestamp
        '''
        i = 0
        all_double_nodes = []
        # if No. of nodes less than two we pass
        if len(self.zoushi_nodes) <= 2:
            return allow_simple_zslx, self.zoushi_nodes[0].time
        
        while i < len(self.zoushi_nodes)-1:
            current_node = self.zoushi_nodes[i]
            next_node = self.zoushi_nodes[i+1]
            dn = Double_Nodes(current_node, next_node)
            all_double_nodes.append(dn)
            i = i + 1
        
        same_direction_nodes = [n for n in all_double_nodes if n.direction == self.direction]
        # make sure the last two slope goes flatten, if not it's NOT exhausted
        # force is only used if we have 5+ xds changed len(same_direction_nodes) < 3 or\
        if len(same_direction_nodes) >= 2 and float_more_equal(abs(same_direction_nodes[-1].work_out_slope()), abs(same_direction_nodes[-2].work_out_slope())):
            if (same_direction_nodes[-1].direction == TopBotType.top2bot and float_less_equal(same_direction_nodes[-2].end.chan_price, same_direction_nodes[-1].end.chan_price)) or\
                (same_direction_nodes[-1].direction == TopBotType.bot2top and float_more_equal(same_direction_nodes[-2].end.chan_price, same_direction_nodes[-1].end.chan_price)) or\
                (
                    float_more_equal(abs(same_direction_nodes[-1].work_out_force()),abs(same_direction_nodes[-2].work_out_force())) and\
                    float_more_equal(abs(same_direction_nodes[-1].work_out_macd_strength()), abs(same_direction_nodes[-2].work_out_macd_strength()))
                ):
                    return False, same_direction_nodes[0].start.time
        return True, same_direction_nodes[-1].start.time
        

class ZhongShu(ZouShiLeiXing):
    '''
    This class store all information of a central region. core data is in the format of pandas series, obtained from iloc
    The first four nodes must be in time order
    '''
    
    def __init__(self, first, second, third, forth, direction, original_df):
        super(ZhongShu, self).__init__(direction, original_df, None)
        self.first = first
        self.second = second
        self.third = third
        self.forth = forth
        self.extra_nodes = []

        self.core_region = []
        self.core_time_region = []
        self.core_amplitude_region = []

        self.get_core_region()
        self.get_core_amplitude_region()
        self.get_core_time_region()
        self.get_amplitude_region()
        self.get_time_region()
        self.isZhongShu=True
    
    def __repr__(self):
        [s, e] = self.get_time_region()
        return "\nZhong Shu {0}:{1}-{2}-{3}-{4} {5}->{6} level@{7}\n[".format(self.direction, self.first.chan_price, self.second.chan_price, self.third.chan_price, self.forth.chan_price, s, e, self.get_level()) + '\n'.join([node.__repr__() for node in self.extra_nodes]) + ']'        
    
    def get_all_nodes(self):
        return self.get_ending_nodes(N=0)
    
    def reverse_nodes(self):
        # method used for reversal analytics
        pass
        
    
    def add_new_nodes(self, tb_nodes, added = False):
        if type(tb_nodes) is list:
            if len(tb_nodes) == 1:
                if tb_nodes[0] != self.first and tb_nodes[0] != self.second and tb_nodes[0] != self.third and tb_nodes[0] != self.forth and tb_nodes[0] not in self.extra_nodes:
                    added = True
                    self.extra_nodes.append(tb_nodes[0])
    
                self.get_amplitude_region(re_evaluate=added)
                self.get_amplitude_region_original(re_evaluate=added)
                self.get_time_region(re_evaluate=added)
            elif len(tb_nodes) > 1:
                if tb_nodes[0] != self.first and tb_nodes[0] != self.second and tb_nodes[0] != self.third and tb_nodes[0] != self.forth and tb_nodes[0] not in self.extra_nodes:
                    added = True
                    self.extra_nodes.append(tb_nodes[0])
                self.add_new_nodes(tb_nodes[1:], added)
        else:
            if tb_nodes != self.first and tb_nodes != self.second and tb_nodes != self.third and tb_nodes != self.forth and tb_nodes not in self.extra_nodes:
                self.extra_nodes.append(tb_nodes)
                self.get_amplitude_region(re_evaluate=True)
                self.get_amplitude_region_original(re_evaluate=True)
                self.get_time_region(re_evaluate=True)
    
    def out_of_zhongshu(self, node1, node2):
        [l,h] = self.get_core_region()
        exit_direction = TopBotType.noTopBot
        if (float_less(node1.chan_price, l) and float_less(node2.chan_price, l)):
            exit_direction = TopBotType.top2bot  
        elif (float_more(node1.chan_price, h) and float_more(node2.chan_price, h)):
            exit_direction = TopBotType.bot2top
        else:
            exit_direction = TopBotType.noTopBot
        return exit_direction
    
    def not_in_core(self, node):
        [l,h] = self.get_core_region()
        return node.chan_price < l or node.chan_price > h
    
    def get_core_region(self):
        upper = 0.0
        lower = 0.0
        if self.direction == TopBotType.bot2top and self.first.tb == self.third.tb == TopBotType.top and self.second.tb == self.forth.tb == TopBotType.bot:
            upper = min(self.first.chan_price, self.third.chan_price)
            lower = max(self.second.chan_price, self.forth.chan_price)
        elif self.direction == TopBotType.top2bot and self.first.tb == self.third.tb == TopBotType.bot and self.second.tb == self.forth.tb == TopBotType.top:
            lower = max(self.first.chan_price, self.third.chan_price)
            upper = min(self.second.chan_price, self.forth.chan_price)
        else:
            print("Invalid central region")       
        self.core_region = [lower, upper] 
        return self.core_region

    def get_core_amplitude_region(self):
        price_list = [self.first.chan_price, self.second.chan_price, self.third.chan_price, self.forth.chan_price]
        self.core_amplitude_region = [min(price_list), max(price_list)]
    
    def get_core_time_region(self, re_evaluate=False):
        if not self.core_time_region or re_evaluate:
            real_start_time = self.original_df[self.first.loc+1]['date']
            self.core_time_region = [real_start_time, self.forth.time]
        return self.core_time_region    
    
    def get_amplitude_region(self, re_evaluate=False):
        if not self.amplitude_region or re_evaluate:
            all_price_list = [self.first.chan_price, self.second.chan_price, self.third.chan_price, self.forth.chan_price] + [node.chan_price for node in self.extra_nodes]
            self.amplitude_region = [min(all_price_list), max(all_price_list)]
        return self.amplitude_region    
    
    def get_amplitude_region_original(self, re_evaluate=False):
        if not self.amplitude_region_origin or re_evaluate:
            [s, e] = self.get_time_diff(re_evaluate)
            region_price_series = self.original_df[s:e+1][['high','low']]
            self.amplitude_region_origin = [region_price_series['low'].min(), region_price_series['high'].max()]
        return self.amplitude_region_origin
        
    def get_amplitude_region_original_without_last_xd(self):
        # used for TYPE I when ZhongShu is the last zoushi
        if self.is_complex_type():
            s_loc = self.first.loc
            e_loc = self.forth.loc if len(self.extra_nodes) == 1 else self.extra_nodes[-2].loc
            region_price_series = self.original_df[s_loc:e_loc+1][['high','low']]
            return [region_price_series['low'].min(), region_price_series['high'].max()]
        else:
            return self.get_amplitude_region_original(re_evaluate=False)
    
    def get_split_zs(self, split_direction, contain_zs=True):
        '''
        higher level Zhong Shu can be split into lower level ones, we can do it at the top or bot nodes
        depends on the given direction of Zous Shi,
        We could split if current Zhong Shu is higher than current level, meaning we are splitting
        at extra_nodes
        Order we can just split on complex ZhongShu
        By default we take all zhongshu nodes
        '''
        node_tb, method = (TopBotType.bot, np.min) if split_direction == TopBotType.bot2top else (TopBotType.top, np.max)
        if self.is_complex_type() or self.get_level().value >= ZhongShuLevel.current.value:
            all_nodes = ([self.first, self.second, self.third, self.forth] if contain_zs else []) + self.extra_nodes
            all_price = [n.chan_price for n in all_nodes]
            ex_price = method(all_price)
            return all_nodes[all_price.index(ex_price):]
        else:
            return []
        
    def get_ending_nodes(self, N=5):
        all_nodes = [self.first, self.second, self.third, self.forth] + self.extra_nodes
        return all_nodes[-N:]

    def get_time_region(self, re_evaluate=False):    
        if not self.time_region or re_evaluate: # assume node stored in time order
            if not self.extra_nodes:
                self.time_region = self.get_core_time_region(re_evaluate)
            else:
                self.extra_nodes.sort(key=lambda x: x.time)
                self.time_region = [self.core_time_region[0], max(self.core_time_region[-1], self.extra_nodes[-1].time)]
        return self.time_region

    def get_level(self):
        # 4 core nodes + 6 extra nodes => 9 xd as next level
        return ZhongShuLevel.current if len(self.extra_nodes) < 6 else ZhongShuLevel.next if 6 <= len(self.extra_nodes) < 24 else ZhongShuLevel.nextnext

    def take_last_xd_as_zslx(self):
        exiting_nodes = [self.third, self.forth] + self.extra_nodes
        if len(exiting_nodes) < 2:
            return ZouShiLeiXing(TopBotType.noTopBot, self.original_df, [])
        else:
            xd = XianDuan(exiting_nodes[-2], exiting_nodes[-1])
            return ZouShiLeiXing(xd.direction, self.original_df, exiting_nodes[-2:])

    def take_first_xd_as_zslx(self):
        return ZouShiLeiXing(TopBotType.reverse(self.direction), self.original_df, [self.first, self.second])

    def take_split_xd_as_zslx(self, split_direction):
        # as we are trying to find a max/min point for the zhongshu we need to take the all nodes
        remaining_nodes = self.get_split_zs(split_direction, contain_zs=True)
        if len(remaining_nodes) < 2:
            return ZouShiLeiXing(TopBotType.noTopBot, self.original_df, [])
        else:
            xd = XianDuan(remaining_nodes[0], remaining_nodes[1])
            return ZouShiLeiXing(xd.direction, self.original_df, remaining_nodes[:2])

    def is_complex_type(self):
        # if the ZhongShu contain more than 3 XD, it's a complex ZhongShu, in practice the direction of it can be interpreted differently
        return bool(self.extra_nodes)

    def isBenZouStyle(self): 
        '''
        check if current Zhongshu is BenZou style
        '''
        if not self.is_complex_type() or len(self.extra_nodes)==1: # we do need this condition
            core_range = self.get_core_region()
            amplitude_range = self.get_amplitude_region_original_without_last_xd()
            core_gap = core_range[1] - core_range[0]
            amplitude_gap = amplitude_range[1] - amplitude_range[0]
            
            if core_gap / amplitude_gap < 0.191: # (1-GOLDEN_RATIO)
                return True
        return False
                
    def get_time_diff(self, re_evaluate=False):
        return [min(self.first.loc, self.extra_nodes[-1].loc), max(self.first.loc, self.extra_nodes[-1].loc)] if self.extra_nodes\
            else [min(self.first.loc, self.forth.loc), max(self.first.loc, self.forth.loc)]

    def get_amplitude_region_between(self, start_loc, end_loc):
        price_series = self.original_df[start_loc:end_loc+1][['high', 'low']]
        return [price_series['low'].min(), price_series['high'].max()]

    def check_exhaustion(self):
        # usually used in panbei type III, just for completeness
        last_xd = self.take_last_xd_as_zslx()
        if self.is_complex_type():
            first_xd = self.take_split_xd_as_zslx(last_xd.direction)
        else:
            first_xd = self.take_first_xd_as_zslx()
            
#         THIS TURNS to be not needed for type III, as it's not a zhongshu by direction
#         so we only need to check exhaustion
#         first_time_diff = first_xd.get_time_diff()
#         last_time_diff = last_xd.get_time_diff()
#         zhongshu_time_diff = [first_time_diff[1], last_time_diff[0]]
#         
#         first_price_region = first_xd.get_amplitude_region_original()
#         last_price_region = last_xd.get_amplitude_region_original()
#         zhongshu_price_region = self.get_core_region()
# #         zhongshu_price_region = self.get_amplitude_region_between(zhongshu_time_diff[0], zhongshu_time_diff[1])
#         
#         balanced = zhongshu_time_diff[0] <= (first_time_diff[0] + last_time_diff[1])/2 <= zhongshu_time_diff[1] and\
#                     zhongshu_price_region[0] <= (max(first_price_region[1],last_price_region[1]) + min(first_price_region[0],last_price_region[0]))/2 <= zhongshu_price_region[1]
        # check exhaustion
        exhausted = float_more(abs(first_xd.work_out_slope()), abs(last_xd.work_out_slope()))
            
        if not exhausted:
            # also need to check balance structure
            core_region = self.get_core_region()
            if first_xd.direction == TopBotType.top2bot == last_xd.direction:
                exhausted = float_more(first_xd.zoushi_nodes[0].chan_price, core_region[1]) and\
                            float_less(last_xd.zoushi_nodes[-1].chan_price, core_region[0]) and\
                            (
                                float_more(abs(first_xd.work_out_force()), abs(last_xd.work_out_force())) or\
                                float_more(abs(first_xd.work_out_macd_strength()), abs(last_xd.work_out_macd_strength()))
                            )
                            
            elif first_xd.direction == TopBotType.bot2top == last_xd.direction:
                exhausted = float_less(first_xd.zoushi_nodes[0].chan_price, core_region[0]) and\
                            float_more(last_xd.zoushi_nodes[-1].chan_price, core_region[1]) and\
                            (
                                float_more(abs(first_xd.work_out_force()), abs(last_xd.work_out_force())) or\
                                float_more(abs(first_xd.work_out_macd_strength()), abs(last_xd.work_out_macd_strength()))
                            )
        return exhausted, last_xd.zoushi_nodes[0].time if exhausted else first_xd.zoushi_nodes[0].time


class CompositeZouShiLeiXing(ZouShiLeiXing):
    '''
    This class contains a combination of XD and zhongshu. We only expect the ZhongShu to be at the 
    same level for this class as precondition
    '''
    def __repr__(self):
        return  'Composite ZSLX:\n' + '\n'.join([zslx.__repr__() for zslx in self.zslx_list])
    
    def __init__(self, zslx_list, original_df):
        super(CompositeZouShiLeiXing, self).__init__(zslx_list[0].direction, original_df, None)
        self.zslx_list = zslx_list
        self.all_zs = [zs for zs in self.zslx_list if type(zs) is ZhongShu]
        self.direction = self.zslx_list[-1].direction

    def get_level(self):
        all_level_value = [zs.get_level().value for zs in self.zslx_list]
        return ZhongShuLevel.value2type(max(all_level_value))
        

    def work_out_slope(self):
        if not self.zslx_list:
            return 0
        
        start_node = self.zslx_list[0].get_first_node_by_direction(self.direction)
        end_node = self.zslx_list[-1].get_last_node_by_direction(self.direction)
        
        return slope_calculation(start_node, end_node)
        
    
    def work_out_force(self):
        if not self.zslx_list:
            return 0
        
        # money
        total_money = sum([zs.get_money_acc() for zs in self.zslx_list])
        
        # amplitude
        all_amplitude = [zs.get_amplitude_region_original() for zs in self.zslx_list]
        min_price = min(list(zip(*all_amplitude))[0])
        max_price = max(list(zip(*all_amplitude))[1])
        
        price_delta = (max_price-min_price) / max_price if self.direction == TopBotType.top2bot else\
                      (max_price-min_price) / min_price
        price_delta *= 100
        
        # time
        start_node = self.zslx_list[0].get_first_node_by_direction(self.direction)
        end_node = self.zslx_list[-1].get_last_node_by_direction(self.direction)
        time_delta = (end_node.loc - start_node.loc) / 1200 * 100
        
        return price_delta * total_money / time_delta ** 2



class CompositeZhongShu(ZouShiLeiXing):
    '''
    This class contains a list of ZouShiLeiXing and Zhongshu which match certain rules and forms combined Zhongshu
    ZhongShu KUOZHAN
    '''
    def __repr__(self):
        return  'Composite ZhongShu:\n' + '\n'.join([zs.__repr__() for zs in self.all_zs])
    
    def __init__(self, zslx_list, original_df):
        super(CompositeZhongShu, self).__init__(zslx_list[0].direction, original_df, None)
        self.zslx_list = zslx_list
        self.all_zs = [zs for zs in self.zslx_list if type(zs) is ZhongShu]
        self.isZhongShu = True
        
    def take_split_xd_as_zslx(self, direction):
        all_first_xd = [zs.take_split_xd_as_zslx(direction) for zs in self.all_zs]
        first_xd = sorted(all_first_xd, key=take_start_price, reverse=direction==TopBotType.top2bot)[0]
        return first_xd
        
    def get_core_region(self):
        [l, u] = self.all_zs[0].get_core_region()
        i = 1
        n_zs = len(self.all_zs)
        while i < n_zs:
            [tl, tu] = self.all_zs[i].get_core_region()
            l = min(l, tl)
            u = max(u, tu)
            i += 1
        return [l, u]
    
    def get_amplitude_region_original_without_last_xd(self):
        [l, u] = self.all_zs[0].get_amplitude_region_original()
        i = 1
        n_zs = len(self.all_zs)
        while i < n_zs:
            if i != n_zs-1:
                [tl, tu] = self.all_zs[i].get_amplitude_region_original()
            else:
                [tl, tu] = self.all_zs[i].get_amplitude_region_original_without_last_xd()
            l = min(l, tl)
            u = max(u, tu)
            i += 1
        return [l, u]
    
    def get_amplitude_region_original(self):
        [l, u] = self.all_zs[0].get_amplitude_region_original()
        i = 1
        n_zs = len(self.all_zs)
        while i < n_zs:
            [tl, tu] = self.all_zs[i].get_amplitude_region_original()
            l = min(l, tl)
            u = max(u, tu)
            i += 1
        return [l, u]
        
    def get_level(self):
        return ZhongShuLevel.next
    
    def isBenZouStyle(self): 
        return False

class ZouShi(object):
    '''
    This class contain the full dissasemble of current zou shi, contains zslx and zs
    '''
    def __init__(self, all_nodes, original_df, isdebug=False):
        self.original_df = original_df
        self.zslx_all_nodes = all_nodes
        self.zslx_result = []
        self.isdebug = isdebug
    
    def split_by_time(self, ts):
        '''
        This method is used after analyze, split the latest zoushi from ts time
        '''
        i = 0
        if ts is None:
            return self.zslx_result
        while i < len(self.zslx_result):
            zs = self.zslx_result[i]
            stime = zs.get_time_region()[0]
            if ts < stime:
                i = i - 1
                break
            elif ts == stime:
                break
            i = i + 1
            
        return self.zslx_result[i:]
        
    
    def sub_zoushi_time(self, chan_type, direction, check_xd_exhaustion=False):
        '''
        This method finds the split DT at high level:
        for zhongshu, we split from top/bot by direction and connect with remaining nodes to form zslx
        for zslx we split from the zhongshu before and connect it with zslx
        
        for both cases above if we checked xd exhaustion, we just need to last XD in the formed zslx
        '''
        if chan_type == Chan_Type.I: # we should end up with zslx - zs - zslx
            if type(self.zslx_result[-1]) is ZouShiLeiXing:
                zs = self.zslx_result[-2]
                zslx = self.zslx_result[-1]
                mark_zslx = zs.take_split_xd_as_zslx(direction) 
                if mark_zslx.isEmpty():
                    mark_zslx = zslx
                pivot_tp = mark_zslx.get_time_region()[0] if not check_xd_exhaustion else zslx.take_last_xd_as_zslx().get_time_region()[0]
                return pivot_tp
            elif type(self.zslx_result[-1]) is ZhongShu:
                zs = self.zslx_result[-1]
                sub_zslx = zs.take_split_xd_as_zslx(direction) if not check_xd_exhaustion else zs.take_last_xd_as_zslx()
                pivot_tp = sub_zslx.get_time_region()[0]
                return pivot_tp
        elif chan_type == Chan_Type.III or chan_type == Chan_Type.III_weak: # we need to split from past top / bot
            if type(self.zslx_result[-1]) is ZouShiLeiXing:
                [s, e] = self.zslx_result[-1].get_time_diff()
                temp_df = self.original_df[s:]
                pivot_tp = temp_df[temp_df['high'].argmax() if direction == TopBotType.top2bot else temp_df['low'].argmin()]['date']
                return pivot_tp
            elif type(self.zslx_result[-1]) is ZhongShu:
                zs = self.zslx_result[-1]
                pivot_tp = zs.get_time_region()[0] if not check_xd_exhaustion else zs.take_last_xd_as_zslx().get_time_region()[0]
                return pivot_tp
        elif chan_type == Chan_Type.II or chan_type == Chan_Type.II_weak:
            if type(self.zslx_result[-1]) is ZouShiLeiXing:
                zslx = self.zslx_result[-1]
                pivot_tp = zslx.get_time_region()[0] if not check_xd_exhaustion else zslx.take_last_xd_as_zslx().get_time_region()[0]
                return pivot_tp
            elif type(self.zslx_result[-1]) is ZhongShu:
                zs = self.zslx_result[-1]
                pivot_tp = zs.take_split_xd_as_zslx(direction).get_time_region()[0] if not check_xd_exhaustion else zs.take_last_xd_as_zslx().get_time_region()[0]
                return pivot_tp
        else:
            return self.zslx_result[-1].get_time_region()[0]

    def analyze(self, initial_direction):
        i = 0
        temp_zslx = ZouShiLeiXing(initial_direction, self.original_df, [])
        previous_node = None
        # reverse all nodes order
#         working_nodes = self.zslx_all_nodes[::-1]
        working_nodes = self.zslx_all_nodes
        
        while i < len(working_nodes) - 1:
            first = working_nodes[i]
            second = working_nodes[i+1]

            third = working_nodes[i+2] if i+2 < len(working_nodes) else None
            forth = working_nodes[i+3] if i+3 < len(working_nodes) else None
            
            if type(temp_zslx) is ZouShiLeiXing:
                if third is not None and forth is not None and ZouShiLeiXing.is_valid_central_region(temp_zslx.direction, first, second, third, forth):
                    # new zs found end previous zslx
                    if not temp_zslx.isEmpty():
                        temp_zslx.add_new_nodes(first)
                        self.zslx_result.append(temp_zslx)
                    # use previous zslx direction for new sz direction
                    temp_zslx = ZhongShu(first, second, third, forth, temp_zslx.direction, self.original_df)
                    if self.isdebug:
                        print("start new Zhong Shu, end previous zslx")
                    previous_node = forth
                    i = i + 2 # use to be 3, but we accept the case where last XD of ZhongShu can be zslx
                else:
                    # continue in zslx
                    temp_zslx.add_new_nodes(first)
                    if self.isdebug:
                        print("continue current zou shi lei xing: {0}".format(temp_zslx))
                    previous_node = first
                    i = i + 1
            else:
                if type(temp_zslx) is ZhongShu: 
                    ed = temp_zslx.out_of_zhongshu(first, second)
                    if ed != TopBotType.noTopBot:
                        # new zsxl going out of zs
                        self.zslx_result.append(temp_zslx)
                        temp_zslx = ZouShiLeiXing(ed, self.original_df, [previous_node])
                        if self.isdebug:
                            print("start new zou shi lei xing, end previous zhong shu")
                    else:
                        # continue in the zs
                        if first != temp_zslx.first and first != temp_zslx.second and first != temp_zslx.third and first != temp_zslx.forth:
                            temp_zslx.add_new_nodes(first)
                        if self.isdebug:
                            print("continue zhong shu: {0}".format(temp_zslx))
                        previous_node = first
                        i = i + 1
        
#         # add remaining nodes
        temp_zslx.add_new_nodes(working_nodes[i:])
        self.zslx_result.append(temp_zslx)

        # reverse back all zslx and nodes within
#         self.zslx_result = self.zslx_result[::-1]

        if self.isdebug:
            print("Zou Shi disassembled: {0}".format(self.zslx_result))

        return self.zslx_result
    
#     @classmethod
#     def get_all_zoushi_nodes(cls, zoushi):
#         if len(zoushi) == 1:
#             return zoushi[0].get_all_nodes()
#         
#         all_nodes = []
#         i = 0
#         while i < len(zoushi):
#             zs = zoushi[i]
#             current_nodes = zs.get_all_nodes()
#             if i == 0:
#                 all_nodes += current_nodes
#             else:
#                 all_nodes += current_nodes[1:]
#             i += 1
#         return all_nodes
    
    @classmethod
    def get_all_zoushi_nodes(cls, zoushi, all_nodes):
        first_node = zoushi[0].get_all_nodes()[0]
        last_node = zoushi[-1].get_all_nodes()[-1]
        first_idx = all_nodes.index(first_node)
        last_idx = all_nodes.index(last_node)
        return all_nodes[first_idx:last_idx+1]
    
    @classmethod
    def analyze_api(cls, initial_direction, zslx_all_nodes, original_df, isdebug=False):
        zslx_result = []
        i = 0
        temp_zslx = ZouShiLeiXing(initial_direction, original_df, [])
        previous_node = None
        while i < len(zslx_all_nodes) - 1:
            first = zslx_all_nodes[i]
            second = zslx_all_nodes[i+1]

            third = zslx_all_nodes[i+2] if i+2 < len(zslx_all_nodes) else None
            forth = zslx_all_nodes[i+3] if i+3 < len(zslx_all_nodes) else None
            
            if type(temp_zslx) is ZouShiLeiXing:
                if third is not None and forth is not None and ZouShiLeiXing.is_valid_central_region(temp_zslx.direction, first, second, third, forth):
                    # new zs found end previous zslx
                    if not temp_zslx.isEmpty():
                        temp_zslx.add_new_nodes(first)
                        zslx_result.append(temp_zslx)
                    # use previous zslx direction for new sz direction
                    temp_zslx = ZhongShu(first, second, third, forth, temp_zslx.direction, original_df)
                    if isdebug:
                        print("start new Zhong Shu, end previous zslx")
                    previous_node = forth
                    i = i + 2 # use to be 3, but we accept the case where last XD of ZhongShu can be zslx
                else:
                    # continue in zslx
                    temp_zslx.add_new_nodes(first)
                    if isdebug:
                        print("continue current zou shi lei xing: {0}".format(temp_zslx))
                    previous_node = first
                    i = i + 1
            else:
                if type(temp_zslx) is ZhongShu: 
                    ed = temp_zslx.out_of_zhongshu(first, second)
                    if ed != TopBotType.noTopBot:
                        # new zsxl going out of zs
                        zslx_result.append(temp_zslx)
                        temp_zslx = ZouShiLeiXing(ed, original_df, [previous_node])
                        if isdebug:
                            print("start new zou shi lei xing, end previous zhong shu")
                    else:
                        # continue in the zs
                        if first != temp_zslx.first and first != temp_zslx.second and first != temp_zslx.third and first != temp_zslx.forth:
                            temp_zslx.add_new_nodes(first)
                        if isdebug:
                            print("continue zhong shu: {0}".format(temp_zslx))
                        previous_node = first
                        i = i + 1
        
#         # add remaining nodes
        temp_zslx.add_new_nodes(zslx_all_nodes[i:])
        zslx_result.append(temp_zslx)

        if isdebug:
            print("Zou Shi disassembled: {0}".format(zslx_result))

        return zslx_result
