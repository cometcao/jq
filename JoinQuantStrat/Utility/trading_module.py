# -*- encoding: utf8 -*-
'''
Created on 10 Oct 2016

@author: MetalInvest
'''
try:
    from easytrader.api import *
    from easytrader.webtrader import WebTrader
    import easytrader.config
except:
    pass
try:
    from kuanke.user_space_api import *
except:
    pass

from api import *
from webtrader import WebTrader

import config
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import traceback
import Crypto
from Crypto.PublicKey import RSA
from Crypto import Random
from Crypto.Hash import MD5

def encryptString(input):
    pass

def copy(path):
    c = read_file(path)
    with open(path, 'wb') as f:
        f.write(c)

def loading(broker, version = 1):
    ''' ��½ '''
    user = use(broker)
    
    # 设置代理IP
    proxy_user = 'user'
    proxy_pwd = 'pwd'
    proxy_ip = '120.78.209.13'
    proxy_port = 9595
    if proxy_ip is not None:
        s = "%s:%s" % (proxy_ip, proxy_port)
        if proxy_user is not None and proxy_pwd is not None:
            s = '%s:%s@%s'%(proxy_user,proxy_pwd,s)
        user.session.proxies = {
            "http": "http://" + s,
            "https": "https://" + s,
        }
    
    if broker == config.trade_acc['use_xq']:
        if version == 1:
            user.prepare(config.trade_acc['json_xq'])
        elif version == 2:
            user.prepare(config.trade_acc['json2_xq'])
        elif version == 3:
            user.prepare(config.trade_acc['json3_xq'])
        else:
            user.prepare(config.trade_acc['json_xq'])
    elif broker == config.trade_acc['use_yjb']:
        copy(config.trade_acc['jar_yjb'])    
        user.prepare(config.trade_acc['json_yjb'])
    elif broker == config.trade_acc['use_ht']:
        copy(config.trade_acc['jar_ht'])
        user.prepare(config.trade_acc['json_ht'])
    return user
    
def check(user):
    ''' 获取信息并输出 '''
#     log.info('获取今日委托单:')
#     log.info('今日委托单:', json.dumps(user.entrust,ensure_ascii=False))
#     log.info('-'*30)
    log.info('获取资金状况:')
    log.info('enable_balance(可用金额):{0}'.format(user.balance[0]['enable_balance']))
    try:
        if user.position:
            log.info('-'*30)
            log.info('持仓:')
            log.info('获取持仓:{0}'.format(str(user.position[0])))
    except:
        pass

# def realAction(stock, pct, data):
#     # all actions mimic market order
#     if 'two_eight_real_action' in config.real_action and config.real_action['two_eight_real_action']:
#         current_data = get_current_data()
#         current_price = 0.0
#         if data:
#             current_price = data[stock].pre_close
#         try:
#             realAction_xq(stock[:6], pct)
#             #realAction_yjb(stock[:6], pct, current_data[stock].high_limit, current_data[stock].low_limit)
#             #pass
#         except:
#             traceback.print_exc()
#             log.info("We have an issue on xue qiu actions!! for stock %s" % stock)
#             send_message("Stock [%s] adjustment to %.2f failed for xue qiu" % (stock, pct), channel='weixin')
#            
#         try:
#             realAction_email(stock[:6], pct, current_price)
#         except:
#             traceback.print_exc()
#             log.info("We have an issue on email actions!! for stock %s" % stock)
#             send_message("Stock [%s] adjustment to %.2f failed for email" % (stock, pct), channel='weixin')

realAction_email_list = []

def realAction_email(stock, value_pct, stock_price):
    global realAction_email_list
    realAction_email_list.append((stock, value_pct, stock_price))
    
def realAction_email_final():
    # make sure we do sell action first
    global realAction_email_list 
    
    if not realAction_email_list:
        return 
    
    realAction_email_list = sorted(realAction_email_list, key=lambda x:x[1])
    
    orders = []
    for stock, value_pct, stock_price in realAction_email_list:
        #orders.append(":".join(map(str,rel)))
        orders.append("%s:%.1f:%.2f" % (stock, value_pct, stock_price))
    orderString = "#".join(orders)
    try:
        sender = 'hprotein@yahoo.com' 
        receiver = 'hprotein@gmail.com' 
        #subject = '{}:{}:{}'.format(stock, value_pct, stock_price) 
        subject = orderString
        smtpserver = 'smtp.mail.yahoo.com' 
        username = 'hprotein@yahoo.com' 
        password = 't198412C'
        
        msg = MIMEText("JQ order",'plain') 
        msg['Subject'] = Header(subject)
        
        server = smtplib.SMTP_SSL(smtpserver)
        #server = smtplib.SMTP(smtpserver)
        #server.set_debuglevel(1)      
        try :
            #server.connect() # ssl��������
            server.login(username, password) 
            server.sendmail(sender, receiver, msg.as_string()) 
            print('order mail success')
        except:
            traceback.print_exc()
            print('order mail failed')
        server.quit() 
    except:
        traceback.print_exc()
        send_message("email with subject order %s failed" % (subject), channel='weixin')
    
    # empty the list
    realAction_email_list = []

def realAction_xq(stock, value_pct):
    user = loading('xq')
    check(user)
    log.info("xue qiu stock [%s] is requested to be adjusted to weight %d pct" %(stock, value_pct))
    user.adjust_weight(stock, int(value_pct))
    
def realAction_xq_2(stock, value_pct):
    user = loading('xq', 2)
    check(user)
    log.info("xue qiu No.2 stock [%s] is requested to be adjusted to weight %d pct" %(stock, value_pct))
    user.adjust_weight(stock, int(value_pct))
    
def realAction_xq_3(stock, value_pct):
    user = loading('xq', 3)
    check(user)
    log.info("xue qiu No.3 stock [%s] is requested to be adjusted to weight %d pct" %(stock, value_pct))
    user.adjust_weight(stock, int(value_pct))
    
def realAction_yjb(stock, value_pct, high, low):
    user = loading('yjb')
    check(user)
    log.info("yong jin bao stock [%s] is requested to be adjusted to weight %d pct" %(stock, value_pct))
    stock_adjust_weight(user, stock, value_pct, high, low)
    time.sleep(2.5)

def stock_adjust_weight(user, stock, value_pct, high, low):
    if value_pct == 0 : # sell stock
        for pos in user.position:
            if pos['stock_code'] == stock and pos['enable_amount'] > 0:
                current_price = pos['last_price']
                own_amount = pos['current_amount']
                sellable_amount = pos['enable_amount']
                if own_amount != sellable_amount:
                    log.info("we have %d unsellable amount" % (own_amount-sellable_amount))
                user.sell(stock, price=low, amount=sellable_amount)
    else:
        port_value = user.balance[0]['current_balance']
        cash = user.balance[0]['enable_balance']
        already_owned = False
        owned_value = 0.0
        for pos in user.position:
            if pos['stock_code'] == stock:
                already_owned = True
                owned_value = pos['market_value']
                break
        expected_value = port_value * value_pct / 100.0
        if already_owned:
            if expected_value > owned_value: # buy some
                delta_value = expected_value - owned_value
                user.buy(stock, price=high, volume=min(cash,delta_value))
            else: # sell some
                delta_value = owned_value - expected_value
                user.sell(stock, price=low, volume=delta_value)
        else:
            user.buy(stock, price=high, volume=min(cash, expected_value))
            
def realAction_ht(stock, value_pct):
    user = loading('ht')
    check(user)
    log.info("hua tai stock [%s] is requested to be adjusted to weight %d pct" %(stock, value_pct))
    
    
class XueQiuAction:
    def __init__(self, cfg, version=1):
        self.retry = 3
        self.config = cfg
        self.version = version
        self.order_list = []
        self.user = None
    
    def reset(self):
        self.order_list = []
        if self.user:
            self.user.exit()
        self.user = None
    
    def connect(self):
        self.user = loading(self.config, self.version)
        check(self.user)
        
    def appendOrder(self, stock, value_pct, stock_price):
        self.order_list.append((stock, value_pct, stock_price))
    
    def hasOrder(self):
        return not self.order_list
    
    def adjustStock(self):
        if self.order_list:
            count = 0
            while count < 3:
                count += 1
                try:
                    if not self.user:
                        self.connect()
                        break
                except Exception as e:
                    log.warn("Xueqiu login failed:" + str(e))
            if count == 3:
                return
            for stock, value_pct, _ in self.order_list:
                try:
                    self.user.adjust_weight(stock, int(value_pct))
                    log.info("xue qiu stock [%s] is requested to be adjusted to weight %d pct" %(stock, value_pct))
                except:
                    log.info('order failed:{0} {1}'.format(stock, value_pct))

# xq = XueQiuAction('xq', 2)
# xq.connect()
# xq.reset()