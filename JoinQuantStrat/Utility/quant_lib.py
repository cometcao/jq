# -*- encoding: utf8 -*-
try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
import numpy as np
import pandas as pd
import datetime as dt


class quantlib():
    def get_fundamentals_sum(self, table_name=indicator, search=indicator.adjusted_profit, statsDate=None):
        # 取最近的五个季度财报的日期
        def __get_quarter(table_name, statsDate):
            '''
            返回最近 n 个财报的日期
            返回每个股票最近一个财报的日期
            '''
            # 取最新一季度的统计日期
            if table_name == 'indicator':
                q = query(indicator.code, indicator.statDate)
            elif table_name == 'income':
                q = query(income.code, income.statDate)
            elif table_name == 'cash_flow':
                q = query(cash_flow.code, cash_flow.statDate)
            elif table_name == 'balance':
                q = query(balance.code, balance.statDate)

            df = get_fundamentals(q, date = statsDate)
            stock_last_statDate = {}
            tmpDict = df.to_dict()
            for i in range(len(tmpDict['statDate'].keys())):
                # 取得每个股票的代码，以及最新的财报发布日
                stock_last_statDate[tmpDict['code'][i]] = tmpDict['statDate'][i]

            df = df.sort(columns='statDate', ascending=False)
            # 取得最新的财报日期
            last_statDate = df.iloc[0,1]

            this_year = int(str(last_statDate)[0:4])
            this_month = str(last_statDate)[5:7]

            if this_month == '12':
                last_quarter       = str(this_year)     + 'q4'
                last_two_quarter   = str(this_year)     + 'q3'
                last_three_quarter = str(this_year)     + 'q2'
                last_four_quarter  = str(this_year)     + 'q1'
                last_five_quarter  = str(this_year - 1) + 'q4'

            elif this_month == '09':
                last_quarter       = str(this_year)     + 'q3'
                last_two_quarter   = str(this_year)     + 'q2'
                last_three_quarter = str(this_year)     + 'q1'
                last_four_quarter  = str(this_year - 1) + 'q4'
                last_five_quarter  = str(this_year - 1) + 'q3'

            elif this_month == '06':
                last_quarter       = str(this_year)     + 'q2'
                last_two_quarter   = str(this_year)     + 'q1'
                last_three_quarter = str(this_year - 1) + 'q4'
                last_four_quarter  = str(this_year - 1) + 'q3'
                last_five_quarter  = str(this_year - 1) + 'q2'

            else:  #this_month == '03':
                last_quarter       = str(this_year)     + 'q1'
                last_two_quarter   = str(this_year - 1) + 'q4'
                last_three_quarter = str(this_year - 1) + 'q3'
                last_four_quarter  = str(this_year - 1) + 'q2'
                last_five_quarter  = str(this_year - 1) + 'q1'
        
            return last_quarter, last_two_quarter, last_three_quarter, last_four_quarter, last_five_quarter, stock_last_statDate

        # 查财报，返回指定值
        def __get_fundamentals_value(table_name, search, myDate):
            '''
            输入查询日期
            返回指定的财务数据，格式 dict
            '''
            if table_name == 'indicator':
                q = query(indicator.code, search, indicator.statDate) 
            elif table_name == 'income':
                q = query(income.code, search, income.statDate)
            elif table_name == 'cash_flow':
                q = query(cash_flow.code, search, cash_flow.statDate)
            elif table_name == 'balance':
                q = query(balance.code, search, balance.statDate)

            df = get_fundamentals(q, statDate = myDate).fillna(value=0)

            tmpDict = df.to_dict()
            stock_dict = {}
            name = str(search).split('.')[-1]
            for i in range(len(tmpDict['statDate'].keys())):
                tmpList = []
                tmpList.append(tmpDict['statDate'][i])
                tmpList.append(tmpDict[name][i])
                stock_dict[tmpDict['code'][i]] = tmpList

            return stock_dict

        
        # 得到最近 n 个季度的统计时间
        last_quarter, last_two_quarter, last_three_quarter, last_four_quarter, last_five_quarter, stock_last_statDate = __get_quarter(table_name, statsDate)
    
        last_quarter_dict       = __get_fundamentals_value(table_name, search, last_quarter)
        last_two_quarter_dict   = __get_fundamentals_value(table_name, search, last_two_quarter)
        last_three_quarter_dict = __get_fundamentals_value(table_name, search, last_three_quarter)
        last_four_quarter_dict  = __get_fundamentals_value(table_name, search, last_four_quarter)
        last_five_quarter_dict  = __get_fundamentals_value(table_name, search, last_five_quarter)

        tmp_list = []
        stock_list = stock_last_statDate.keys()
        for stock in stock_list:
            tmp_dict = {}
            tmp_dict['code'] = stock
            value_list = []
            if stock in last_quarter_dict:
                if stock_last_statDate[stock] == last_quarter_dict[stock][0]:
                    value_list.append(last_quarter_dict[stock][1])

            if stock in last_two_quarter_dict:
                value_list.append(last_two_quarter_dict[stock][1])

            if stock in last_three_quarter_dict:
                value_list.append(last_three_quarter_dict[stock][1])

            if stock in last_four_quarter_dict:
                value_list.append(last_four_quarter_dict[stock][1])

            if stock in last_five_quarter_dict:
                value_list.append(last_five_quarter_dict[stock][1])

            for i in range(4 - len(value_list)):
                value_list.append(0)
            
            tmp_dict['0Q'] = value_list[0]
            tmp_dict['1Q'] = value_list[1]
            tmp_dict['2Q'] = value_list[2]
            tmp_dict['3Q'] = value_list[3]
            tmp_dict['sum_value'] = value_list[0] + value_list[1] + value_list[2] + value_list[3]
            tmp_list.append(tmp_dict)
        df = pd.DataFrame(tmp_list)

        return df

    def fun_set_var(self, context, var_name, var_value):
        if var_name not in dir(context):
            setattr(context, var_name, var_value)

    def fun_check_price(self, algo_name, stock_list, position_price, gap_trigger):
        flag = False
        msg = ""
        if stock_list:
            h = history(1, '1d', 'close', stock_list, df=False)
            for stock in stock_list:
                curPrice = h[stock][0]
                if stock not in position_price:
                    position_price[stock] = curPrice
                oldPrice = position_price[stock]
                if oldPrice != 0:
                    deltaprice = abs(curPrice - oldPrice)
                    if deltaprice / oldPrice > gap_trigger:
                        msg = algo_name + "需要调仓: " + stock + "，现价: " + str(curPrice) + " / 原价格: " + str(oldPrice) + "\n"
                        flag = True
                        return flag, position_price, msg
        return flag, position_price, msg

    def fun_needRebalance(self,context, algo_name, moneyfund, stock_list, position_price, hold_periods, hold_cycle, gap_trigger):
        msg = ""
        rebalance_flag = False
        
        
        stocks_count = 0
        for stock in stock_list:
            if stock not in moneyfund:
                stocks_count += 1
        if stocks_count == 0:
            msg += algo_name + "调仓，因为持股数为 0 \n"
            rebalance_flag = True
        elif hold_periods == 0:
            msg += algo_name + "调仓，因为持股天数剩余为 0 \n"
            rebalance_flag = True
        if not rebalance_flag:
            rebalance_flag, position_price, msg2 = self.fun_check_price(algo_name, stock_list, position_price, gap_trigger)
            msg += msg2
        if rebalance_flag:
            hold_periods = hold_cycle
        else:
            hold_periods -= 1
        msg += algo_name + "离下次调仓还剩 " + str(hold_periods) + " 天\n"
        
        

        return rebalance_flag, position_price, hold_periods, msg
        
    def stock_clean_by_ma(self,context,security,short=4,long=40):
        #检查均线是否多头
        ma_short = attribute_history(security, short, '1d', ('close'), True).mean()['close']
        ma_long = attribute_history(security, long, '1d', ('close'), True).mean()['close']
        record(ma_short=ma_short,ma_long=ma_long)
        if ma_short <= ma_long and ma_short>3300:
            return True
        else:
            
            return False
    
    def stock_clean_by_mom(self,context):
        gr_index2 = self.get_growth_rate(context.index2)
        gr_index8 = self.get_growth_rate(context.index8)
        if (gr_index2 <= context.index_growth_rate and  gr_index8 <= context.index_growth_rate):
            return True
        else:
            return False
            
    def equity_curve_protect(self,context):
        if not context.is_day_curve_protect:
            cur_value = context.portfolio.total_value
            if len(context.value_list) >= 20:
                last_value = context.value_list[-20]
                avg_value = sum(context.value_list[-20:]) / 20
                if cur_value < last_value*0.99:
                    #if cur_value < avg_value:
                    log.info("==> 启动资金曲线保护, 20日前资产: %f, 当前资产: %f" %(last_value, cur_value))
                    context.is_day_curve_protect = True
    
        if context.is_day_curve_protect:
            context.curve_protect_days = -2

        return context.is_day_curve_protect
    
    def reset_param(self,context):
        context.is_day_curve_protect = False
            
    def get_pe_median(self,context):
        scanDate = context.previous_date
        q = query(valuation.code, valuation.pe_ratio)
        df =get_fundamentals(q, scanDate).dropna()
        df['ep_ratio'] = 1/df['pe_ratio']
        
        print('pe_ratio median:', 1/df['ep_ratio'].quantile(0.5))
        #print(df.head())
        #pe中位数控制仓位
        context.pe_ratio_median = 1/df['ep_ratio'].quantile(0.5)
        record(pe=context.pe_ratio_median)
        
       
            
    # 更新持有股票的价格，每次调仓后跑一次
    def fun_update_positions_price(self, ratio):
        position_price = {}
        if ratio:
            h = history(1, '1m', 'close', ratio.keys(), df=False)
            for stock in ratio.keys():
                if ratio[stock] > 0:
                    position_price[stock] = round(h[stock][0], 3)
        return position_price

    def fun_assetAllocationSystem(self, stock_list, moneyfund, confidencelevel, statsDate=None):
        def __fun_getEquity_ratio(__stocklist, confidencelevel, type, limit_up=1.0, limit_low=0.0, statsDate=None):
            __ratio = {}
            if __stocklist:
                if type == 1: #风险平价 历史模拟法
                # 正态分布概率表，标准差倍数以及置信率
                # 1.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
                    __ratio = self.fun_calStockWeight_by_risk(confidencelevel, __stocklist, limit_up, limit_low, statsDate)
                elif type == 2: #马科维奇
                    __ratio = self.fun_calStockWeight(__stocklist, limit_up, limit_low)
                elif type == 3: #最小方差
                    __ratio = self.fun_cal_Weight_by_minvar(__stocklist, limit_up, limit_low)
                elif type == 5: # 风险平价 方差-协方差法
                    __ratio = self.fun_calWeight_by_RiskParity(__stocklist, statsDate)
                else: #等权重
                    for stock in __stocklist:
                        __ratio[stock] = 1.0/len(__stocklist)

            return __ratio

        if stock_list:
            limit_up, limit_low = round(2.0/len(list(set(stock_list))), 4), round(0.5/len(list(set(stock_list))), 4)
            equity_ratio = __fun_getEquity_ratio(stock_list, confidencelevel, 0, limit_up, limit_low, statsDate)
        else:
            equity_ratio = {}
        bonds_ratio  = __fun_getEquity_ratio(moneyfund, confidencelevel, 0, 1.0, 0.0, statsDate)

        return equity_ratio, bonds_ratio

    def fun_calPosition(self, equity_ratio, bonds_ratio, algo_ratio, risk_ratio, moneyfund, portfolio_value, confidencelevel, statsDate=None):
        '''
        equity_ratio 资产配仓结果
        bonds_ratio 债券配仓结果
        algo_ratio 策略占市值的百分比
        risk_ratio 每个标的承受的风险系数
        '''
        trade_ratio = equity_ratio # 简化

        return trade_ratio

    # 去极值
    def fun_winsorize(self, rs, type, num):
        # rs为Series化的数据
        rs = rs.dropna().copy()
        low_line, up_line = 0, 0
        if type == 1:   # 标准差去极值
            mean = rs.mean()
            #取极值
            mad = num*rs.std()
            up_line  = mean + mad
            low_line = mean - mad
        elif type == 2: #中位值去极值
            rs = rs.replace([-np.inf, np.inf], np.nan)
            median = rs.median()
            md = abs(rs - median).median()
            mad = md * num * 1.4826
            up_line = median + mad
            low_line = median - mad
        elif type == 3: #Boxplot 去极值
            if len(rs) < 2:
                return rs
            mc = sm.stats.stattools.medcouple(rs)
            rs.sort()
            q1 = rs[int(0.25*len(rs))]
            q3 = rs[int(0.75*len(rs))]
            iqr = q3-q1        
            if mc >= 0:
                    low_line = q1-1.5*np.exp(-3.5*mc)*iqr
                    up_line = q3+1.5*np.exp(4*mc)*iqr        
            else:
                    low_line = q1-1.5*np.exp(-4*mc)*iqr
                    up_line = q3+1.5*np.exp(3.5*mc)*iqr

        rs[rs < low_line] = low_line
        rs[rs > up_line] = up_line
        
        return rs

    #标准化
    def fun_standardize(self, s,type):
        '''
        s为Series数据
        type为标准化类型:1 MinMax,2 Standard,3 maxabs 
        '''
        data=s.dropna().copy()
        if int(type)==1:
            rs = (data - data.min())/(data.max() - data.min())
        elif type==2:
            rs = (data - data.mean())/data.std()
        elif type==3:
            rs = data/10**np.ceil(np.log10(data.abs().max()))
        return rs

    #中性化
    def fun_neutralize(self, s, df, module='pe_ratio', industry_type=None, level=2, statsDate=None):
        '''
        参数：
        s为stock代码 如'000002.XSHE' 可为list,可为str
        moduel:中性化的指标 默认为PE
        industry_type:行业类型(可选), 如果行业不指定，全市场中性化
        返回：
        中性化后的Series index为股票代码 value为中性化后的值
        '''
        s = df[df.code.isin(list(s))]
        s = s.reset_index(drop = True)
        s = pd.Series(s[module].values, index=s['code'])
        s = self.fun_winsorize(s,1,3)

        if industry_type:
            stocks = self.fun_get_industry_stocks(industry=industry_type, level=level, statsDate=statsDate)
        else:
            stocks = list(get_all_securities(['stock'], date=statsDate).index)

        df = df[df.code.isin(stocks)]
        df = df.reset_index(drop = True)
        df = pd.Series(df[module].values, index=df['code'])
        df = self.fun_winsorize(df,1, 3)
        rs = (s - df.mean())/df.std()

        return rs

    def fun_get_factor(self, df, factor_name, industry, level, statsDate):
        stock_list = self.fun_get_industry_stocks(industry, level, statsDate)
        rs = self.fun_neutralize(stock_list, df, module=factor_name, industry_type=industry, level=level, statsDate=statsDate)
        rs = self.fun_standardize(rs, 2)

        return rs

    def fun_diversity_by_industry(self, stock_list, max_num, statsDate):
        if not stock_list:
            return stock_list

        industry_list = self.fun_get_industry(cycle=None)
        tmpList = []
        for industry in industry_list:
            i = 0
            stocks = self.fun_get_industry_stocks(industry, 2, statsDate)
            for stock in stock_list:
                if stock in stocks: #by 行业选入 top max_num 的标的（如有）
                    i += 1
                    if i <= max_num:
                        tmpList.append(stock) #可能一个股票横跨多个行业，会导致多次入选，但不影响后面计算
        final_stocks = []
        for stock in stock_list:
            if stock in tmpList:
                final_stocks.append(stock)
        return final_stocks

    # 根据行业取股票列表
    def fun_get_industry_stocks(self, industry, level=2, statsDate=None):
        if level == 2:
            stock_list = get_industry_stocks(industry, statsDate)
        elif level == 1:
            industry_list = self.fun_get_industry_levelI(industry)
            stock_list = []
            for industry_code in industry_list:
                tmpList = get_industry_stocks(industry_code, statsDate)
                stock_list = stock_list + tmpList
            stock_list = list(set(stock_list))
        else:
            stock_list = []

        return stock_list

    # 一级行业列表
    def fun_get_industry_levelI(self, industry=None):
        industry_dict = {
            'A':['A01', 'A02', 'A03', 'A04', 'A05'] #农、林、牧、渔业
            ,'B':['B06', 'B07', 'B08', 'B09', 'B11'] #采矿业
            ,'C':['C13', 'C14', 'C15', 'C17', 'C18', 'C19', 'C20', 'C21', 'C22', 'C23', 'C24', 'C25', 'C26', 'C27', 'C28', 'C29', 'C30', 'C31', 'C32',\
                'C33', 'C34', 'C35', 'C36', 'C37', 'C38', 'C39', 'C40', 'C41', 'C42'] #制造业
            ,'D':['D44', 'D45', 'D46'] #电力、热力、燃气及水生产和供应业
            ,'E':['E47', 'E48', 'E50'] #建筑业
            ,'F':['F51', 'F52'] #批发和零售业
            ,'G':['G53', 'G54', 'G55', 'G56', 'G58', 'G59']    #交通运输、仓储和邮政业
            ,'H':['H61', 'H62'] #住宿和餐饮业
            ,'I':['I63', 'I64', 'I65']    #信息传输、软件和信息技术服务业
            ,'J':['J66', 'J67', 'J68', 'J69']    #金融业
            ,'K':['K70']    #房地产业
            ,'L':['L71', 'L72']    #租赁和商务服务业
            ,'M':['M73', 'M74']    #科学研究和技术服务业
            ,'N':['N78']    #水利、环境和公共设施管理业
            #,'O':[] #居民服务、修理和其他服务业
            ,'P':['P82']    #教育
            ,'Q':['Q83']    #卫生和社会工作
            ,'R':['R85', 'R86', 'R87'] #文化、体育和娱乐业
            ,'S':['S90']    #综合
            }
        if industry == None:
            return industry_dict
        else:
            return industry_dict[industry]

    # 行业列表
    def fun_get_industry(self, cycle=None):
        # cycle 的参数：None取所有行业，True取周期性行业，False取非周期性行业
        industry_dict = {
            'A01':False,# 农业     1993-09-17
            'A02':False,# 林业     1996-12-06
            'A03':False,# 畜牧业     1997-06-11
            'A04':False,# 渔业     1993-05-07
            'A05':False,# 农、林、牧、渔服务业     1997-05-30
            'B06':True, # 煤炭开采和洗选业     1994-01-06
            'B07':True, # 石油和天然气开采业     1996-06-28
            'B08':True, # 黑色金属矿采选业     1997-07-08
            'B09':True, # 有色金属矿采选业     1996-03-20
            'B11':True, # 开采辅助活动     2002-02-05
            'C13':False, #    农副食品加工业     1993-12-15
            'C14':False,# 食品制造业     1994-08-18
            'C15':False,# 酒、饮料和精制茶制造业     1992-10-12
            'C17':True,# 纺织业     1992-06-16
            'C18':True,# 纺织服装、服饰业     1993-12-31
            'C19':True,# 皮革、毛皮、羽毛及其制品和制鞋业     1994-04-04
            'C20':False,# 木材加工及木、竹、藤、棕、草制品业     2005-05-10
            'C21':False,# 家具制造业     1996-04-25
            'C22':False,# 造纸及纸制品业     1993-03-12
            'C23':False,# 印刷和记录媒介复制业     1994-02-24
            'C24':False,# 文教、工美、体育和娱乐用品制造业     2007-01-10
            'C25':True, # 石油加工、炼焦及核燃料加工业     1993-10-25
            'C26':True, # 化学原料及化学制品制造业     1990-12-19
            'C27':False,# 医药制造业     1993-06-29
            'C28':True, # 化学纤维制造业     1993-07-28
            'C29':True, # 橡胶和塑料制品业     1992-08-28
            'C30':True, # 非金属矿物制品业     1992-02-28
            'C31':True, # 黑色金属冶炼及压延加工业     1994-01-06
            'C32':True, # 有色金属冶炼和压延加工业     1996-02-15
            'C33':True, # 金属制品业     1993-11-30
            'C34':True, # 通用设备制造业     1992-03-27
            'C35':True, # 专用设备制造业     1992-07-01
            'C36':True, # 汽车制造业     1992-07-24
            'C37':True, # 铁路、船舶、航空航天和其它运输设备制造业     1992-03-31
            'C38':True, # 电气机械及器材制造业     1990-12-19
            'C39':False,# 计算机、通信和其他电子设备制造业     1990-12-19
            'C40':False,# 仪器仪表制造业     1993-09-17
            'C41':True, # 其他制造业     1992-08-14
            'C42':False,# 废弃资源综合利用业     2012-10-26
            'D44':True, # 电力、热力生产和供应业     1993-04-16
            'D45':False,# 燃气生产和供应业     2000-12-11
            'D46':False,# 水的生产和供应业     1994-02-24
            'E47':True, # 房屋建筑业     1993-04-29
            'E48':True, # 土木工程建筑业     1994-01-28
            'E50':True, # 建筑装饰和其他建筑业     1997-05-22
            'F51':False,# 批发业     1992-05-06
            'F52':False,# 零售业     1992-09-02
            'G53':True, # 铁路运输业     1998-05-11
            'G54':True, # 道路运输业     1991-01-14
            'G55':True, # 水上运输业     1993-11-19
            'G56':True, # 航空运输业     1997-11-05
            'G58':True, # 装卸搬运和运输代理业     1993-05-05
            'G59':False,# 仓储业     1996-06-14
            'H61':False,# 住宿业     1993-11-18
            'H62':False,# 餐饮业     1997-04-30
            'I63':False,# 电信、广播电视和卫星传输服务     1992-12-02
            'I64':False,# 互联网和相关服务     1992-05-07
            'I65':False,# 软件和信息技术服务业     1992-08-20
            'J66':True, # 货币金融服务     1991-04-03
            'J67':True, # 资本市场服务     1994-01-10
            'J68':True, # 保险业     2007-01-09
            'J69':True, # 其他金融业     2012-10-26
            'K70':True, # 房地产业     1992-01-13
            'L71':False,# 租赁业     1997-01-30
            'L72':False,# 商务服务业     1996-08-29
            'M73':False,# 研究和试验发展     2012-10-26
            'M74':True, # 专业技术服务业     2007-02-15
            'N77':False,# 生态保护和环境治理业     2012-10-26
            'N78':False,# 公共设施管理业     1992-08-07
            'P82':False,# 教育     2012-10-26
            'Q83':False,# 卫生     2007-02-05
            'R85':False,# 新闻和出版业     1992-12-08
            'R86':False,# 广播、电视、电影和影视录音制作业     1994-02-24
            'R87':False,# 文化艺术业     2012-10-26
            'S90':False,# 综合     1990-12-10
            }

        industry_list = []
        if cycle == True:
            for industry in industry_dict.keys():
                if industry_dict[industry] == True:
                    industry_list.append(industry)
        elif cycle == False:
            for industry in industry_dict.keys():
                if industry_dict[industry] == False:
                    industry_list.append(industry)
        else:
            industry_list = industry_dict.keys()

        return industry_list

    def fun_do_trade(self, context, trade_ratio, moneyfund, trade_style):

        def __fun_tradeBond(context, stock, curPrice, Value):
            curValue = float(context.portfolio.positions[stock].total_amount * curPrice)
            deltaValue = abs(Value - curValue)
            if deltaValue > (curPrice*200):
                if Value > curValue:
                    cash = context.portfolio.cash
                    if cash > (curPrice*200):
                        self.fun_trade(context, stock, Value)
                        
                else:
                    self.fun_trade(context, stock, Value)

        def __fun_tradeStock(context, curPrice, stock, ratio, trade_style):
            total_value = context.portfolio.portfolio_value
            if stock in moneyfund:
                __fun_tradeBond(context, stock, curPrice, total_value * ratio)
            else:
                curValue = context.portfolio.positions[stock].total_amount * curPrice
                Quota = total_value * ratio
                if Quota:
                    if abs(Quota - curValue) / Quota >= 0.25 or trade_style:
                        if Quota > curValue:
                            #if curPrice > context.portfolio.positions[stock].avg_cost:
                            self.fun_trade(context, stock, Quota)
                            
                        else:
                            self.fun_trade(context, stock, Quota)
                else:
                    if curValue > 0:
                        self.fun_trade(context, stock, Quota)
    
        trade_list = trade_ratio.keys()
        myholdstock = context.portfolio.positions.keys()
        stock_list = list(set(trade_list).union(set(myholdstock)))
        total_value = context.portfolio.portfolio_value
    
        # 已有仓位
        holdDict = {}
        h = history(1, '1d', 'close', stock_list, df=False)
        for stock in myholdstock:
            tmpW = round((context.portfolio.positions[stock].total_amount * h[stock])/total_value, 2)
            holdDict[stock] = float(tmpW)
    
        # 对已有仓位做排序
        tmpDict = {}
        for stock in holdDict:
            if stock in trade_ratio:
                tmpDict[stock] = round((trade_ratio[stock] - holdDict[stock]), 2)
        tradeOrder = sorted(tmpDict.items(), key=lambda d:d[1], reverse=False)

        # 交易已有仓位的股票，从减仓的开始，腾空现金
        _tmplist = []
        for idx in tradeOrder:
            stock = idx[0]
            __fun_tradeStock(context, h[stock][-1], stock, trade_ratio[stock], trade_style)
            _tmplist.append(stock)

        # 交易新股票
        for i in range(len(trade_list)):
            stock = trade_list[i]
            if len(_tmplist) != 0 :
                if stock not in _tmplist:
                    __fun_tradeStock(context, h[stock][-1], stock, trade_ratio[stock], trade_style)
            else:
                __fun_tradeStock(context, h[stock][-1], stock, trade_ratio[stock], trade_style)

    def unpaused(self, stock_list, positions_list):
        current_data = get_current_data()
        tmpList = []
        for stock in stock_list:
            if not current_data[stock].paused or stock in positions_list:
                tmpList.append(stock)
        return tmpList

    def remove_st(self, stock_list, statsDate):
        current_data = get_current_data()
        return [s for s in stock_list if not current_data[s].is_st]

    def remove_limit_up(self, stock_list, positions_list):
        h = history(1, '1m', 'close', stock_list, df=False, skip_paused=False, fq='pre')
        h2 = history(1, '1m', 'high_limit', stock_list, df=False, skip_paused=False, fq='pre')
        tmpList = []
        for stock in stock_list:
            if h[stock][0] < h2[stock][0] or stock in positions_list:
                tmpList.append(stock)

        return tmpList

    def fun_get_bad_stock_list(self, statsDate):
        #0、剔除商誉占比 > 10% 的股票
        df = get_fundamentals(
            query(valuation.code, balance.good_will, balance.equities_parent_company_owners),
            date = statsDate
        )

        df = df.fillna(value = 0)
        df['good_will_ratio'] = 1.0*df['good_will'] / df['equities_parent_company_owners']
        list_good_will = list(df[df.good_will_ratio > 0.1].code)

        bad_stocks = list_good_will
        bad_stocks = list(set(bad_stocks))
        return bad_stocks

    def remove_bad_stocks(self, stock_list, bad_stock_list):
        tmpList = []
        for stock in stock_list:
            if stock not in bad_stock_list:
                tmpList.append(stock)
        return tmpList

    # 剔除上市时间较短的产品
    def fun_delNewShare(self, context, equity, deltaday):
        deltaDate = context.current_dt.date() - dt.timedelta(deltaday)
    
        tmpList = []
        for stock in equity:
            if get_security_info(stock).start_date < deltaDate:
                tmpList.append(stock)
    
        return tmpList

    def fun_trade(self, context, stock, value):
        self.fun_setCommission(context, stock)
        order_target_value(stock, value)

    def fun_setCommission(self, context, stock):
        if stock in context.moneyfund:
            set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0, close_commission=0, close_today_commission=0, min_commission=0), type='fund')
        else:
            set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003, close_today_commission=0, min_commission=5), type='stock')
    def get_portfolio_info_text(self,context,op_sfs=[0]):
        
        sub_str = ''
        table = PrettyTable(["仓号","股票", "持仓", "当前价", "盈亏率","持仓比"])  
        for sf_id in range(len(context.subportfolios)):
            cash = context.subportfolios[sf_id].cash
            p_value = context.subportfolios[sf_id].positions_value
            total_values = p_value +cash
            if sf_id in op_sfs:
                sf_id_str = str(sf_id) + ' *'
            else:
                sf_id_str = str(sf_id)
            for stock in context.subportfolios[sf_id].long_positions.keys():
                position = context.subportfolios[sf_id].long_positions[stock]
                if sf_id in op_sfs and stock in context.op_buy_stocks:
                    stock_str = self.show_stock(stock) + ' *'
                else:
                    stock_str = self.show_stock(stock)
                stock_raite = (position.total_amount * position.price) / total_values * 100
                table.add_row([sf_id_str,
                    stock_str,
                    position.total_amount,
                    position.price,
                    "%.2f%%"%((position.price - position.avg_cost) / position.avg_cost * 100), 
                    "%.2f%%"%(stock_raite)]
                    )
            if sf_id < len(context.subportfolios) - 1:
                table.add_row(['----','---------------','-----','----','-----','-----'])
            sub_str += '[仓号: %d] [总值:%d] [持股数:%d] [仓位:%.2f%%] \n'%(sf_id,
                total_values,
                len(context.subportfolios[sf_id].long_positions)
                ,p_value*100/(cash+p_value))
        
        print ('子仓详情:\n' + sub_str + str(table))
    def show_stock(self,stock):
        return "%s %s"%(stock[:6],get_security_info(stock).display_name)
    # 清空卖出所有持仓
    def clear_position(self,context):
        def close_position(position):
            security = position.security
            order = order_target_value(security, 0)
            
        if context.portfolio.positions:
            log.info("==> 清仓，卖出所有股票")
            context.hold_periods = 0
            for stock in context.portfolio.positions.keys():
                position = context.portfolio.positions[stock]
                close_position(position)
    
        
    def get_growth_rate(self,security, n=20):
        lc = self.get_close_price(security, n)
        #c = data[security].close
        c = self.get_close_price(security, 1, '1m')
        
        if not isnan(lc) and not isnan(c) and lc != 0:
            return (c - lc) / lc
        else:
            log.error("数据非法, security: %s, %d日收盘价: %f, 当前价: %f" %(security, n, lc, c))
            return 0
    
    def get_close_price(self,security, n, unit='1d'):
        return attribute_history(security, n, unit, ('close'), True)['close'][0]
