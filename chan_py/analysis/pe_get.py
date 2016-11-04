# 计算股票的PEG值
# 输入：context(见API)；stock_list为list类型，表示股票池
# 输出：df_PEG为dataframe: index为股票代码，data为相应的PEG值
def get_PEG(context, stock_list): 
    # 查询股票池里股票的市盈率，收益增长率
    q_PE_G = query(valuation.code, valuation.pe_ratio, indicator.inc_net_profit_year_on_year
                 ).filter(valuation.code.in_(stock_list)) 
    # 得到一个dataframe：包含股票代码、市盈率PE、收益增长率G
    # 默认date = context.current_dt的前一天,使用默认值，避免未来函数，不建议修改
    df_PE_G = get_fundamentals(q_PE_G)
    # 筛选出成长股：删除市盈率或收益增长率为负值的股票
    df_Growth_PE_G = df_PE_G[(df_PE_G.pe_ratio >0)&(df_PE_G.inc_net_profit_year_on_year >0)]
    # 去除PE或G值为非数字的股票所在行
    df_Growth_PE_G.dropna()
    # 得到一个Series：存放股票的市盈率TTM，即PE值
    Series_PE = df_Growth_PE_G.ix[:,'pe_ratio']
    # 得到一个Series：存放股票的收益增长率，即G值
    Series_G = df_Growth_PE_G.ix[:,'inc_net_profit_year_on_year']
    # 得到一个Series：存放股票的PEG值
    Series_PEG = Series_PE/Series_G
    # 将股票与其PEG值对应
    Series_PEG.index = df_Growth_PE_G.ix[:,0]
    # 将Series类型转换成dataframe类型
    df_PEG = pd.DataFrame(Series_PEG)
    return df_PEG
    
#7
# 获得买入信号
# 输入：context(见API)
# 输出：list_to_buy为list类型,表示待买入的g.num_stocks支股票
def stocks_to_buy(context):
    list_to_buy = []
    # 得到一个dataframe：index为股票代码，data为相应的PEG值
    df_PEG = get_PEG(context, g.feasible_stocks)
    # 将股票按PEG升序排列，返回daraframe类型
    df_sort_PEG = df_PEG.sort(columns=[0], ascending=[1])
    # 将存储有序股票代码index转换成list并取前g.num_stocks个为待买入的股票，返回list
    for i in range(g.num_stocks):
        if df_sort_PEG.ix[i,0] < 0.5:
            list_to_buy.append(df_sort_PEG.index[i])
    return list_to_buy

