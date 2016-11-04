'''
Created on 2 Oct 2016

@author: MetalInvest
'''

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
              maximum_advacne_margin = 1.21,
              minimum_divergence_margin_upper = 1.02,
              minimum_divergence_margin_lower = 0.98,
              minimum_fallback_margin = 0.3
              )

