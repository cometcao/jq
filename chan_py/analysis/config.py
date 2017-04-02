'''
Created on 2 Oct 2016

@author: MetalInvest
'''


########################################## Trade param ########################################
stop_loss = dict(
            stop_loss_conservative = 0.98,
            stop_loss_aggressive = 0.93,
            stop_loss_normal = 0.95     
                 )

stop_gain = dict(
            stop_gain_conservative = 1.03,
            stop_gain_aggressvie = 1.13,
            stop_gain_normal = 1.07
                 )

margin = dict(
              minimum_advance_margin = 1.13,
              maximum_advacne_margin = 0.30,
              minimum_divergence_margin_upper = 1.02,
              minimum_divergence_margin_lower = 0.98,
              minimum_fallback_margin = 0.20
              )

############################################# Trade control ##############################################

trade_margin = dict(
                    buy_extra_margin = 1.03,
                    sell_extra_margin = 0.97
                    )

trade_acc = dict(
                use_xq = 'xq', # 
                json_xq = 'xq.json', # two_eight
                json2_xq = 'xq_2.json', # macd
                json3_xq = 'xq_3.json', # backup
                use_yjb = 'yjb',
                use_ht = 'ht',
                json_yjb = 'yjb.json',
                json_ht = 'ht.json',
                jar_yjb = 'yjb_verify_code.jar',
                jar_ht = 'getcode_jdk1.5.jar'
                )

real_action = dict(
                macd_real_action = True,
                two_eight_real_action = True
                )

fja5 = [
    u'150008.XSHE', u'150018.XSHE', u'150030.XSHE', u'150051.XSHE', u'150076.XSHE',
    u'150083.XSHE', u'150085.XSHE', u'150088.XSHE', u'150090.XSHE', u'150092.XSHE', 
    u'150094.XSHE', u'150100.XSHE', u'150104.XSHE', u'150106.XSHE', u'150108.XSHE', 
    u'150112.XSHE', u'150117.XSHE', u'150121.XSHE', u'150123.XSHE', u'150130.XSHE', 
    u'150135.XSHE', u'150140.XSHE', u'150145.XSHE', u'150148.XSHE', u'150150.XSHE', 
    u'150152.XSHE', u'150157.XSHE', u'150171.XSHE', u'150173.XSHE', u'150177.XSHE', 
    u'150179.XSHE', u'150181.XSHE', u'150184.XSHE', u'150186.XSHE', u'150190.XSHE', 
    u'150192.XSHE', u'150194.XSHE', u'150196.XSHE', u'150198.XSHE', u'150203.XSHE', 
    u'150205.XSHE', u'150207.XSHE', u'150209.XSHE', u'150213.XSHE', u'150215.XSHE', 
    u'150217.XSHE', u'150221.XSHE', u'150225.XSHE', u'150227.XSHE', u'150241.XSHE', 
    u'150247.XSHE', u'150249.XSHE', u'150255.XSHE', u'150267.XSHE', u'150271.XSHE', 
    u'150291.XSHE', u'150295.XSHE', u'150299.XSHE', u'502001.XSHG', u'502004.XSHG', 
    u'502007.XSHG', u'502011.XSHG', u'502014.XSHG', u'502021.XSHG', u'502024.XSHG', 
    u'502027.XSHG', u'502031.XSHG', u'502037.XSHG', u'502041.XSHG', u'502049.XSHG', 
    u'502054.XSHG', u'502057.XSHG']