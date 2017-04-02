'''
Created on 6 Oct 2016

@author: MetalInvest
'''

def isDeathCross(i,j, macd):
    # if macd sign change, we detect an immediate cross
    # sign changed from -val to +val and 
    if i == 0:
        return False
    if j<0 and macd[i-1] >0:
        return True
    return False

def isGoldCross(i,j, macd):
    # if macd sign change, we detect an immediate cross
    # sign changed from -val to +val and 
    if i == 0:
        return False
    if j>0 and macd[i-1] <0:
        return True
    return False

def checkAtBottomDoubleCross_chan(df):
    # shortcut
    if not (df.shape[0] > 2 and df['macd'][-1] < 0 and df['macd'][-1] > df['macd'][-2]):
        return False
    
    # gold
    mask = df['macd'] > 0
    mask = mask[mask==True][mask.shift(1) == False]
    
    # death
    mask2 = df['macd'] < 0
    mask2 = mask2[mask2==True][mask2.shift(1)==False]
    
    try:
        gkey1 = mask.keys()[-1]
        dkey2 = mask2.keys()[-2]
        dkey1 = mask2.keys()[-1]
        recent_low = previous_low = 0.0
        if g.botUseZvalue:
            low_mean = df.loc[dkey2:,'low'].mean(axis=0)
            low_std = df.loc[dkey2:,'low'].std(axis=0)
            df.loc[dkey2:, 'low_z'] = (df.loc[dkey2:,'low'] - low_mean) / low_std
            
            recent_low = df.loc[dkey1:,'low_z'].min(axis=0)
            previous_low = df.loc[dkey2:gkey1, 'low_z'].min(axis=0)
        else:
            recent_low = df.loc[dkey1:,'low'].min(axis=0)
            previous_low = df.loc[dkey2:gkey1, 'low'].min(axis=0)
            
        recent_min_idx = df.loc[dkey1:,'low'].idxmin()
        loc = df.index.get_loc(recent_min_idx)
        recent_min_idx_nx = df.index[loc+1]
        recent_area_est = abs(df.loc[dkey1:recent_min_idx_nx, 'macd'].sum(axis=0)) * 2
        # recent_red_area = df.loc[gkey1:dkey1, 'macd'].sum(axis=0)
        
        previous_area = abs(df.loc[dkey2:gkey1, 'macd'].sum(axis=0))
        previous_close = df['close'][-1]
        
        result =  df.macd[-2] < df.macd[-1] < 0 and \
                0 > df.macd_raw[-1] and \
                recent_area_est < previous_area and \
                previous_low >= recent_low and \
                df.loc[dkey2,'vol_ma'] > df.vol_ma[-1]
                # abs (recent_low / previous_low) > g.lower_ratio_range
                # recent_area_est < recent_red_area and \
                # > df.macd_raw[recent_min_idx]
                #previous_low >= recent_low and \
                #previous_close / df.loc[recent_min_idx, 'close'] < g.upper_ratio_range
                # abs (recent_low / previous_low) > g.lower_ratio_range
                
        return result
    except IndexError:
        return False
        
def checkAtTopDoubleCross_chan(df):
    if not (df['macd'][-1] > 0 and df['macd'][-1] < df['macd'][-2]):
        return False
    
    # gold
    mask = df['macd'] > 0
    mask = mask[mask==True][mask.shift(1) == False]
    
    # death
    mask2 = df['macd'] < 0
    mask2 = mask2[mask2==True][mask2.shift(1)==False]
    
    try:
        gkey1 = mask.keys()[-1]
        gkey2 = mask.keys()[-2]
        dkey1 = mask2.keys()[-1]
        recent_high = previous_high = 0.0
        if g.topUseZvalue:
            high_mean = df.loc[gkey2:,'high'].mean(axis=0)
            high_std = df.loc[gkey2:,'high'].std(axis=0)
            df.loc[gkey2:, 'high_z'] = (df.loc[gkey2:,'high'] - high_mean) / high_std       
            
            recent_high = df.loc[gkey1:,'high_z'].min(axis=0)
            previous_high = df.loc[gkey2:dkey1, 'high_z'].min(axis=0)
        else:
            recent_high = df.loc[gkey1:,'high'].max(axis=0)
            previous_high = df.loc[gkey2:dkey1, 'high'].max(axis=0)
        
        recent_high_idx = df.loc[gkey1:,'high'].idxmax()
        loc = df.index.get_loc(recent_high_idx)
        recent_high_idx_nx = df.index[loc+1]
        recent_area_est = df.loc[gkey1:recent_high_idx_nx, 'macd'].sum(axis=0) * 2
        previous_area = df.loc[gkey2:dkey1, 'macd'].sum(axis=0)
        return df.macd[-2] > df.macd[-1] > 0 and \
                df.macd_raw[recent_high_idx] > df.macd_raw[-1] > 0 and \
                recent_area_est < previous_area and \
                recent_high >= previous_high
                # abs(recent_high / previous_high) > g.lower_ratio_range
    except IndexError:
        return False

def checkAtBottomDoubleCross_v2(df):
    # bottom divergence gold
    mask = df['macd'] > 0
    mask = mask[mask==True][mask.shift(1) == False]#[mask.shift(2)==False]
    
    mask2 = df['macd'] < 0
    mask2 = mask2[mask2==True][mask2.shift(1)==False]#[mask2.shift(2)==False]#[mask2.shift(-1)==True]
    try:
        dkey2 = mask2.keys()[-2]
        dkey1 = mask2.keys()[-1]
        
        gkey2 = mask.keys()[-2]
        gkey1 = mask.keys()[-1]
        
        result = df.loc[dkey2:gkey2, 'close'].min(axis=0) > df.loc[dkey1:gkey1, 'close'].min(axis=0) and \
               df.macd_raw[gkey2] < df.macd_raw[gkey1] < 0 and \
               df.loc[dkey2:gkey2, 'macd_raw'].min(axis=0) < df.loc[dkey1:gkey1, 'macd_raw'].min(axis=0) and \
               df.macd[-2] < 0 < df.macd[-1] and \
               df.loc[dkey2,'vol_ma'] > df.vol_ma[-1]
        return result
    except IndexError:
        return False

def macd_top_divergence(df, context):
    df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = MACD(df['close'].values)
    return checkAtTopDoubleCross_chan(df) 

def macd_bottom_divergence(context, stock):
    df = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check, ('high', 'low', 'open', 'close', 'volume'), df=True)
    if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
        return False
    
    df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = MACD(df['close'].values)
    # df.loc[:,'OBV'] = talib.OBV(df['close'].values,double(df['volume'].values))
    df.loc[:,'vol_ma'] = talib.SMA(df['volume'].values, 5)
    df = df.dropna()

    #checkResult = checkAtBottomDoubleCross_chan(df)
    checkResult = checkAtBottomDoubleCross_v2(df)
    return checkResult 

def zscore(series):
    return (series - series.mean()) / np.std(series)
