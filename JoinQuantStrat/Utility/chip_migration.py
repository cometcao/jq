'''
Created on 14 Jan 2017

@author: MetalInvest
'''
from kuanke.user_space_api import *
from copy import deepcopy
############################### initial attempt, work out the cumulative turnover ratio ####################################
############################### and concentration based on price range #####################################################
def cumsum_tr_concentration(df):
    global assumed_starting_point
    df['tr_cum'] = df.ix[::-1, 'turnover_ratio'].cumsum()[::-1]
    df_work = df[df['tr_cum']<=assumed_starting_point]
    row_size,col_size = df_work.shape
    df['trailing_high'] = pd.rolling_max(df['high'].shift(-row_size+1).fillna(0), window=row_size)
    df['trailing_low'] = pd.rolling_min(df['low'].shift(-row_size+1).fillna(999), window=row_size)
    df['concentration_rate'] = df['tr_cum'] / (df['trailing_high'] - df['trailing_low'])
    df_work = df[df['tr_cum']<=assumed_starting_point]
#     print (df_work)
#     print (df_work.loc[:,['avg','volume','turnover_ratio','concentration_rate']])

    plt.plot(df_work['avg'].index, df_work['concentration_rate'])
    plt.ylabel('concentration_rate')
    plt.xlabel('date')
######################################### per 100 turnover rate, check the relative price range ##############################
def initialIndex(df, collective_tr_sum):
    total = 0
    row_size, _ = df.shape
    for i in range(0, row_size):
        dai = df.index[i]
        total += df.loc[dai, 'turnover_ratio']
        if total > collective_tr_sum:
            return i
    return 0

def fixed_tr_price_range_concentration(df, stock, con_ratio):
    collective_tr_sum = 200
    row_size, _ = df.shape
    ii = initialIndex(df, collective_tr_sum)
    for i in range(ii, row_size):
        dai = df.index[i]
        current_sum = df.loc[dai, 'turnover_ratio']
        j = i
        while (j > 0) and (current_sum < collective_tr_sum):
            current_sum += df.loc[df.index[j], 'turnover_ratio']
            j -= 1
        sub_work = df.loc[df.index[j:i+1], ['high', 'low']]
        df.loc[dai, 'sub_concentration'] = current_sum / (sub_work['high'].max() - sub_work['low'].min())
    df = df.dropna()
    a, b = linreg(df['sub_concentration'].values, range(0, len(df.index)))
#     print ("stock %s with param %.2f" % (get_security_info(stock).display_name, b))
    con_ratio.append((b, get_security_info(stock).display_name))

##############################################################################################################################
################################## chip migration simulation ##############################
def chip_migration(df):
    collective_tr_sum = 100
    row_size, _ = df.shape
    ii = initialIndex(df, collective_tr_sum)
    if ii == row_size-1:
        df.ix[-1, 'chip_density'] = 0
        return df
    
    initialDate = df.index[0]
    initialEndDate = df.index[ii]
    # build initial chip view
    initial_df = df.iloc[:ii+1]
#     chip_view = deepcopy(initial_df)
    chip_view = initial_df.groupby('avg').agg({'turnover_ratio':'sum'})
    chip_sum = chip_view.ix[:,'turnover_ratio'].sum()
    # chips decay
    decay_df = df.iloc[ii+1:]
    for da, item in decay_df.iterrows():
        avg = item['avg']
        tr = item['turnover_ratio']
        chip_view = chip_change(avg, tr, chip_view)
        wave_range = (chip_view.index[-1] - chip_view.index[0]) / chip_view.index[0]
        density = chip_sum / wave_range
        df.loc[da, 'chip_density'] = density
    return df

def chip_change(avg, tr, chip_view):
    work_out_change_portion(avg, chip_view, tr)

    # remove old chips
    chip_view['turnover_ratio'] -= chip_view['moved_tr']
    
    while True:
        # for negative value on turnover_ratio
        dealing_tr_mask = chip_view['turnover_ratio'] < 0 

        # with negative tr we need to move it to adjacent price level
        profit_mask = dealing_tr_mask[dealing_tr_mask==True][dealing_tr_mask.shift(1)==False]
        for p in profit_mask.keys():
            current_p_index = chip_view.index.get_loc(p)
            offset = 1
            if chip_view.ix[p, 'pct_change'] > 0:
                offset = -1
            print chip_view
            previous_index = chip_view.index[current_p_index+offset]
            chip_view.loc[previous_index, 'turnover_ratio'] += chip_view.loc[p, 'turnover_ratio']
            chip_view.loc[p, 'turnover_ratio'] = 0
            
        loss_mask = dealing_tr_mask[dealing_tr_mask==True][dealing_tr_mask.shift(-1)==False]
        for p in loss_mask.keys():
            current_p_index = chip_view.index.get_loc(p)
            offset = 1
            if chip_view.ix[p, 'pct_change'] > 0:
                offset = -1
            print chip_view
            next_index = chip_view.index[current_p_index+offset]            
            chip_view.loc[next_index, 'turnover_ratio'] += chip_view.loc[p, 'turnover_ratio']
            chip_view.loc[p, 'turnover_ratio'] = 0         
        # after all moves, we remove any price level wth only pos tr left
        chip_view = chip_view[chip_view.turnover_ratio != 0]
        if (chip_view.turnover_ratio>0).all():
            break
    
    # add current chips
    if avg in chip_view.index:
        chip_view.loc[avg, 'turnover_ratio'] += tr
    else:
        chip_view.loc[avg, 'turnover_ratio'] = tr
    return chip_view.sort_index()
        
def work_out_change_portion(avg, chip_view, tr):
    chip_view['pct_change'] = (chip_view.index - avg)/avg
    total_change = abs(chip_view['pct_change']).sum()
    chip_view['change_portion'] = abs(chip_view['pct_change'])/total_change
    chip_view['moved_tr'] = chip_view['change_portion'] * tr
