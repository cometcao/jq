#!/usr/local/bin/python2.7
# encoding: utf-8
'''
biaoLiStatus -- shortdesc

biaoLiStatus is a description

It defines classes_and_methods

@author:     MetalInvestor

@copyright:  2017 organization_name. All rights reserved.

@license:    license

@contact:    user_email
@deffield    updated: Updated
'''
from enum import Enum 
import numpy as np

class InclusionType(Enum):
    # output: 0 = no inclusion, 1 = first contains second, 2 second contains first
    noInclusion = 0
    firstCsecond = 2
    secondCfirst = 3
    
class TopBotType(Enum):
    noTopBot = 0
    top = 1
    bot = -1

class KBarStatus(Enum):
    upTrendNode = (1, 0)
    upTrend = (1, 1)
    downTrendNode = (-1, 0)
    downTrend = (-1, 1)
    none_status = (np.nan, np.nan)
    def __le__(self, b):
        result = False
        if self.value[0] < b.value[0]:
            result = True
        elif self.value[0] > b.value[0]:
            result = False
        else: # == case
            if self.value[1] <= b.value[1]:
                result = True
            else:
                result = False
        return result

class StatusCombo(Enum):
    @staticmethod
    def matchStatus(*parameters):
        pass
    
class StatusValue(object):
    @classmethod
    def matchBiaoLiStatus(cls, *params):
        first = params[0]
        second = params[1]
        return first == cls.status[0] and second == cls.status[1]
    @classmethod
    def testClassmethod(cls):
        print(type(cls.status[0]))

class DownNodeDownNode(StatusValue):
    status = (KBarStatus.downTrendNode, KBarStatus.downTrendNode) # (-1, 0) (-1, 0)
    
class DownNodeUpTrend(StatusValue):
    status = (KBarStatus.downTrendNode, KBarStatus.upTrend) # (-1, 0) (1, 1)
    
class DownNodeUpNode(StatusValue):
    status = (KBarStatus.downTrendNode, KBarStatus.upTrendNode) # (-1, 0) (-1, 0)
    
class UpNodeUpNode(StatusValue):
    status = (KBarStatus.upTrendNode, KBarStatus.upTrendNode)     # (1, 0) (1, 0)
    
class UpNodeDownTrend(StatusValue):
    status = (KBarStatus.upTrendNode, KBarStatus.downTrend)      # (1, 0) (-1, 1)
    
class UpNodeDownNode(StatusValue):
    status = (KBarStatus.upTrendNode, KBarStatus.downTrendNode)   # (1, 0) (-1, 0)

class DownTrendDownTrend(StatusValue):
    status = (KBarStatus.downTrend, KBarStatus.downTrend)         # (-1, 1) (-1, 1)
    
class DownTrendDownNode(StatusValue):
    status = (KBarStatus.downTrend, KBarStatus.downTrendNode)    # (-1, 1) (-1, 0)

class DownNodeDownTrend(StatusValue):
    status = (KBarStatus.downTrendNode, KBarStatus.downTrend) # (-1, 0) (-1, 1)

class UpTrendUpTrend(StatusValue):
    status = (KBarStatus.upTrend, KBarStatus.upTrend)             # (1, 1) (1, 1)
    
class UpTrendUpNode(StatusValue):
    status = (KBarStatus.upTrend, KBarStatus.upTrendNode)        # (1, 1) (1, 0)
    
class UpNodeUpTrend(StatusValue):
    status = (KBarStatus.upTrendNode, KBarStatus.upTrend)         # (1, 0) (1, 1)

class DownTrendUpNode(StatusValue):
    status = (KBarStatus.downTrend, KBarStatus.upTrendNode)# (-1, 1) (1, 0)
    
class DownTrendUpTrend(StatusValue): 
    status = (KBarStatus.downTrend, KBarStatus.upTrend)   # (-1, 1) (1, 1)

class UpTrendDownNode(StatusValue):
    status = (KBarStatus.upTrend, KBarStatus.downTrendNode)# (1, 1) (-1, 0)
    
class UpTrendDownTrend(StatusValue):
    status = (KBarStatus.upTrend, KBarStatus.downTrend)   # (1, 1) (-1, 1)  

class LongPivotCombo(StatusCombo):
    downNodeDownNode = (KBarStatus.downTrendNode, KBarStatus.downTrendNode) # (-1, 0) (-1, 0)
    downNodeUpTrend = (KBarStatus.downTrendNode, KBarStatus.upTrend)      # (-1, 0) (1, 1)
    downNodeUpNode = (KBarStatus.downTrendNode, KBarStatus.upTrendNode)   # (-1, 0) (1, 0)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == LongPivotCombo.downNodeDownNode.value[0] and second == LongPivotCombo.downNodeDownNode.value[1]) or \
            (first == LongPivotCombo.downNodeUpNode.value[0] and second == LongPivotCombo.downNodeUpNode.value[1]) or \
            (first == LongPivotCombo.downNodeUpTrend.value[0] and second == LongPivotCombo.downNodeUpTrend.value[1]):
            return True
        return False

class ShortPivotCombo(StatusCombo):
    upNodeUpNode = (KBarStatus.upTrendNode, KBarStatus.upTrendNode)     # (1, 0) (1, 0)
    upNodeDownTrend = (KBarStatus.upTrendNode, KBarStatus.downTrend)      # (1, 0) (-1, 1)
    upNodeDownNode = (KBarStatus.upTrendNode, KBarStatus.downTrendNode)   # (1, 0) (-1, 0)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == ShortPivotCombo.upNodeUpNode.value[0] and second == ShortPivotCombo.upNodeUpNode.value[1]) or \
            (first == ShortPivotCombo.upNodeDownTrend.value[0] and second == ShortPivotCombo.upNodeDownTrend.value[1]) or \
            (first == ShortPivotCombo.upNodeDownNode.value[0] and second == ShortPivotCombo.upNodeDownNode.value[1]):
            return True
        return False

class ShortStatusCombo(StatusCombo):
    downTrendDownTrend = (KBarStatus.downTrend, KBarStatus.downTrend)         # (-1, 1) (-1, 1)
    downTrendDownNode = (KBarStatus.downTrend, KBarStatus.downTrendNode)    # (-1, 1) (-1, 0)
    downNodeDownTrend = (KBarStatus.downTrendNode, KBarStatus.downTrend) # (-1, 0) (-1, 1)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == ShortStatusCombo.downTrendDownTrend.value[0] and second == ShortStatusCombo.downTrendDownTrend.value[1]) or \
            (first == ShortStatusCombo.downTrendDownNode.value[0] and second == ShortStatusCombo.downTrendDownNode.value[1]) or \
            (first == ShortStatusCombo.downNodeDownTrend.value[0] and second == ShortStatusCombo.downNodeDownTrend.value[1]):
            return True
        return False
    
class LongStatusCombo(StatusCombo):
    upTrendUpTrend = (KBarStatus.upTrend, KBarStatus.upTrend)             # (1, 1) (1, 1)
    upTrendUpNode = (KBarStatus.upTrend, KBarStatus.upTrendNode)        # (1, 1) (1, 0)
    upNodeUpTrend = (KBarStatus.upTrendNode, KBarStatus.upTrend)         # (1, 0) (1, 1)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == LongStatusCombo.upTrendUpTrend.value[0] and second == LongStatusCombo.upTrendUpTrend.value[1]) or \
            (first == LongStatusCombo.upTrendUpNode.value[0] and second == LongStatusCombo.upTrendUpNode.value[1]) or \
            (first == LongStatusCombo.upNodeUpTrend.value[0] and second == LongStatusCombo.upNodeUpTrend.value[1]):
            return True
        return False

class StatusQueCombo(StatusCombo):
    downTrendUpNode = (KBarStatus.downTrend, KBarStatus.upTrendNode)# (-1, 1) (1, 0)
    downTrendUpTrend = (KBarStatus.downTrend, KBarStatus.upTrend)   # (-1, 1) (1, 1)
    upTrendDownNode = (KBarStatus.upTrend, KBarStatus.downTrendNode)# (1, 1) (-1, 0)
    upTrendDownTrend = (KBarStatus.upTrend, KBarStatus.downTrend)   # (1, 1) (-1, 1)  
    
# DownNodeDownNode.testClassmethod()