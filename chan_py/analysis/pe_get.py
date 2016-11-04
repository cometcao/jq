# �����Ʊ��PEGֵ
# ���룺context(��API)��stock_listΪlist���ͣ���ʾ��Ʊ��
# �����df_PEGΪdataframe: indexΪ��Ʊ���룬dataΪ��Ӧ��PEGֵ
def get_PEG(context, stock_list): 
    # ��ѯ��Ʊ�����Ʊ����ӯ�ʣ�����������
    q_PE_G = query(valuation.code, valuation.pe_ratio, indicator.inc_net_profit_year_on_year
                 ).filter(valuation.code.in_(stock_list)) 
    # �õ�һ��dataframe��������Ʊ���롢��ӯ��PE������������G
    # Ĭ��date = context.current_dt��ǰһ��,ʹ��Ĭ��ֵ������δ���������������޸�
    df_PE_G = get_fundamentals(q_PE_G)
    # ɸѡ���ɳ��ɣ�ɾ����ӯ�ʻ�����������Ϊ��ֵ�Ĺ�Ʊ
    df_Growth_PE_G = df_PE_G[(df_PE_G.pe_ratio >0)&(df_PE_G.inc_net_profit_year_on_year >0)]
    # ȥ��PE��GֵΪ�����ֵĹ�Ʊ������
    df_Growth_PE_G.dropna()
    # �õ�һ��Series����Ź�Ʊ����ӯ��TTM����PEֵ
    Series_PE = df_Growth_PE_G.ix[:,'pe_ratio']
    # �õ�һ��Series����Ź�Ʊ�����������ʣ���Gֵ
    Series_G = df_Growth_PE_G.ix[:,'inc_net_profit_year_on_year']
    # �õ�һ��Series����Ź�Ʊ��PEGֵ
    Series_PEG = Series_PE/Series_G
    # ����Ʊ����PEGֵ��Ӧ
    Series_PEG.index = df_Growth_PE_G.ix[:,0]
    # ��Series����ת����dataframe����
    df_PEG = pd.DataFrame(Series_PEG)
    return df_PEG
    
#7
# ��������ź�
# ���룺context(��API)
# �����list_to_buyΪlist����,��ʾ�������g.num_stocks֧��Ʊ
def stocks_to_buy(context):
    list_to_buy = []
    # �õ�һ��dataframe��indexΪ��Ʊ���룬dataΪ��Ӧ��PEGֵ
    df_PEG = get_PEG(context, g.feasible_stocks)
    # ����Ʊ��PEG�������У�����daraframe����
    df_sort_PEG = df_PEG.sort(columns=[0], ascending=[1])
    # ���洢�����Ʊ����indexת����list��ȡǰg.num_stocks��Ϊ������Ĺ�Ʊ������list
    for i in range(g.num_stocks):
        if df_sort_PEG.ix[i,0] < 0.5:
            list_to_buy.append(df_sort_PEG.index[i])
    return list_to_buy

