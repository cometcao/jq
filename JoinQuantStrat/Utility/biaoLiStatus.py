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

class StatusCombo(Enum):
    @staticmethod
    def matchStatus(*parameters):
        pass
    @classmethod
    def matchBiaoLiStatus(cls, *params):
        first = params[0]
        second = params[1]
        return first == cls.status.value[0] and second == cls.status.value[1]

class DownNodeDownNode(StatusCombo):
    status = (KBarStatus.downTrendNode, KBarStatus.downTrendNode) # (-1, 0) (-1, 0)
    @staticmethod
    def matchStatus(*params):
        first = params[0]
        second = params[1]
        return first == DownNodeDownNode.status.value[0] and second == DownNodeDownNode.status.value[1]
    
class DownNodeUpTrend(StatusCombo):
    status = (KBarStatus.downTrendNode, KBarStatus.upTrend) # (-1, 0) (1, 1)
    
class DownNodeUpNode(StatusCombo):
    status = (KBarStatus.downTrendNode, KBarStatus.upTrendNode) # (-1, 0) (-1, 0)
    
class UpNodeUpNode(StatusCombo):
    status = (KBarStatus.upTrendNode, KBarStatus.upTrendNode)     # (1, 0) (1, 0)
    
class UpNodeDownTrend(StatusCombo):
    status = (KBarStatus.upTrendNode, KBarStatus.downTrend)      # (1, 0) (-1, 1)
    
class UpNodeDownNode(StatusCombo):
    status = (KBarStatus.upTrendNode, KBarStatus.downTrendNode)   # (1, 0) (-1, 0)

class DownTrendDownTrend(StatusCombo):
    status = (KBarStatus.downTrend, KBarStatus.downTrend)         # (-1, 1) (-1, 1)
    
class DownTrendDownNode(StatusCombo):
    status = (KBarStatus.downTrend, KBarStatus.downTrendNode)    # (-1, 1) (-1, 0)

class DownNodeDownTrend(StatusCombo):
    status = (KBarStatus.downTrendNode, KBarStatus.downTrend) # (-1, 0) (-1, 1)

class UpTrendUpTrend(StatusCombo):
    status = (KBarStatus.upTrend, KBarStatus.upTrend)             # (1, 1) (1, 1)
    
class UpTrendUpNode(StatusCombo):
    status = (KBarStatus.upTrend, KBarStatus.upTrendNode)        # (1, 1) (1, 0)
    
class UpNodeUpTrend(StatusCombo):
    status = (KBarStatus.upTrendNode, KBarStatus.upTrend)         # (1, 0) (1, 1)

class DownTrendUpNode(StatusCombo):
    status = (KBarStatus.downTrend, KBarStatus.upTrendNode)# (-1, 1) (1, 0)
    
class DownTrendUpTrend(StatusCombo): 
    status = (KBarStatus.downTrend, KBarStatus.upTrend)   # (-1, 1) (1, 1)

class UpTrendDownNode(StatusCombo):
    status = (KBarStatus.upTrend, KBarStatus.downTrendNode)# (1, 1) (-1, 0)
    
class UpTrendDownTrend(StatusCombo):
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
    