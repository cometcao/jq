# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *
except:
    pass
from jqdata import *
from oop_record_stats import Op_stocks_record
from oop_strategy_frame import *
from trading_module import *
try:
    import shipane_sdk
    import trader_sync
except:
    log.error("加载 shipane_sdk和trader_sync失败")
    pass

'''=================================实盘易相关================================='''

'''-----------------根据XueQiuOrder下单------------------------'''
class XueQiu_order(Op_stocks_record):
    def __init__(self,params):
        self.version = params.get('version',3)
        self.xueqiu = XueQiuAction('xq', self.version)
        pass
        
    def update_params(self, context, params):
        self.__init__(params)
        
    def after_trading_end(self,context):
        self.xueqiu.reset()
        pass
        
        # 调仓后调用
    def after_adjust_end(self,context,data):
        self.xueqiu.adjustStock()
        self.xueqiu.reset()

    def on_clear_position(self, context, pindex=[0]):
        self.xueqiu.adjustStock()
        self.xueqiu.reset()  

    # 卖出股票时调用的函数
    def on_sell_stock(self,position,order,is_normal,pindex=0,context=None):
        try:
            # if not order.is_buy:
            target_amount = 0 if order.action == 'close' and order.status == OrderStatus.held else position.total_amount
            target_pct = target_amount * order.price / context.portfolio.total_value * 100
            self.log.info("xue qiu sell %s to target %s" % (position.security, target_pct))
            self.xueqiu.appendOrder(order.security[:6], target_pct, 0)
            pass
        except:
            self.log.error('雪球交易失败:' + str(order))
        pass
    
    # 买入股票时调用的函数
    def on_buy_stock(self,stock,order,pindex=0,context=None):
        try:
            # if order.is_buy:
            target_amount = context.portfolio.positions[stock].total_amount if order.status == OrderStatus.held else order.filled
            target_pct = target_amount * order.price / context.portfolio.total_value * 100
            self.log.info("xue qiu buy %s to target %s" % (stock, target_pct))
            self.xueqiu.appendOrder(order.security[:6], target_pct, 0)
            pass
        except:
            self.log.error('雪球交易失败:' + str(order))
        pass
    def __str__(self):
        return '雪球跟踪盘'


# '''-------------------实盘易对接 同步持仓-----------------------'''
class Shipane_manager(Op_stocks_record):
    def __init__(self, params):
        Op_stocks_record.__init__(self, params)
        try:
            log
            self._logger = shipane_sdk._Logger()
        except NameError:
            import logging
            self._logger = logging.getLogger()
        self.moni_trader = JoinQuantTrader()
        self.shipane_trader = ShipaneTrader(self._logger, **params)
        self.syncer = TraderSynchronizer(self._logger
                                         , self.moni_trader
                                         , self.shipane_trader
                                         , normalize_code=normalize_code
                                         , **params)
        self._cost = params.get('cost', 100000)
        self._source_trader_record = []
        self._dest_trader_record = []

    def update_params(self, context, params):
        Op_stocks_record.update_params(self, context, params)
        self._cost = params.get('cost', 100000)
        self.shipane_trader = ShipaneTrader(self._logger, **params)
        self.syncer = TraderSynchronizer(self._logger
                                         , self.moni_trader
                                         , self.shipane_trader
                                         , normalize_code=normalize_code
                                         , **params)

    def after_adjust_end(self, context, data):
        # 是否指定只在有发生调仓动作时进行调仓
        if self._params.get('sync_with_change', True):
            if self.position_has_change:
                self.syncer.execute(context, data)
        else:
            self.syncer.execute(context, data)
        self.position_has_change = False

    def on_clear_position(self, context, pindex=[0]):
        if self._params.get('sync_with_change', True):
            if self.position_has_change:
                self.syncer.execute(context, None)
        else:
            self.syncer.execute(context, None)
        self.position_has_change = False

    def after_trading_end(self, context):
        Op_stocks_record.after_trading_end(self, context)
        try:
            self.moni_trader.context = context
            self.shipane_trader.context = context
            # 记录模拟盘市值
            pf = self.moni_trader.portfolio
            self._source_trader_record.append([self.moni_trader.current_dt, pf.positions_value + pf.available_cash])
            # 记录实盘市值
            pf = self.shipane_trader.portfolio
            self._dest_trader_record.append([self.shipane_trader.current_dt, pf.positions_value + pf.available_cash])
            self._logger.info('[实盘管理器] 实盘涨幅统计:\n' + self.get_rate_str(self._dest_trader_record))
            self._logger.info('[实盘管理器] 实盘持仓统计:\n' + self._get_trader_portfolio_text(self.shipane_trader))
        except Exception as e:
            self._logger.error('[实盘管理器] 盘后数据处理错误!' + str(e))

    def get_rate_str(self, record):
        if len(record) > 1:
            if record[-2][1] == 0:
                return '穷鬼，你没钱，还统计啥'
            rate_total = (record[-1][1] - self._cost) / self._cost
            rate_today = (record[-1][1] - record[-2][1]) / record[-2][1]
            now = datetime.datetime.now()
            record_week = [x for x in record if (now - x[0]).days <= 7]
            rate_week = (record[-1][1] - record_week[0][1]) / record_week[0][1] if len(record_week) > 0 else 0
            record_mouth = [x for x in record if (now - x[0]).days <= 30]
            rate_mouth = (record[-1][1] - record_mouth[0][1]) / record_mouth[0][1] if len(record_mouth) > 0 else 0
            return '资产涨幅:[总:%.2f%%] [今日%.2f%%] [最近一周:%.2f%%] [最近30:%.2f%%]' % (
                rate_total * 100
                , rate_today * 100
                , rate_week * 100
                , rate_mouth * 100)
        else:
            return '数据不足'
        pass

    # 获取持仓信息，HTML格式
    def _get_trader_portfolio_html(self, trader):
        pf = trader.portfolio
        total_values = pf.positions_value + pf.available_cash
        position_str = "总资产: [ %d ]<br>市值: [ %d ]<br>现金   : [ %d ]<br>" % (
            total_values,
            pf.positions_value, pf.available_cash
        )
        position_str += "<table border=\"1\"><tr><th>股票代码</th><th>持仓</th><th>当前价</th><th>盈亏</th><th>持仓比</th></tr>"
        for position in pf.positions.values():
            stock = position.security
            if position.price - position.avg_cost > 0:
                tr_color = 'red'
            else:
                tr_color = 'green'
            stock_raite = (position.total_amount * position.price) / total_values * 100
            position_str += '<tr style="color:%s"><td> %s </td><td> %d </td><td> %.2f </td><td> %.2f%% </td><td> %.2f%%</td></tr>' % (
                tr_color,
                show_stock(normalize_code(stock)),
                position.total_amount, position.price,
                (position.price - position.avg_cost) / position.avg_cost * 100,
                stock_raite
            )

        return position_str + '</table>'

    # 获取持仓信息，普通文本格式
    def _get_trader_portfolio_text(self, trader):
        pf = trader.portfolio
        total_values = pf.positions_value + pf.available_cash
        position_str = "总资产 : [ %d ] 市值: [ %d ] 现金   : [ %d ]" % (
            total_values,
            pf.positions_value, pf.available_cash
        )

        table = PrettyTable(["股票", "持仓", "当前价", "盈亏", "持仓比"])
        for stock in pf.positions.keys():
            position = pf.positions[stock]
            if position.total_amount == 0:
                continue
            stock_str = show_stock(normalize_code(stock))
            stock_raite = (position.total_amount * position.price) / total_values * 100
            table.add_row([
                stock_str,
                position.total_amount,
                position.price,
                "%.2f%%" % ((position.price - position.avg_cost) / position.avg_cost * 100),
                "%.2f%%" % (stock_raite)]
            )
        return position_str + '\n' + str(table)

    def __str__(self):
        return '实盘管理类:[同步持仓] [实盘邮件] [实盘报表]'


# '''------------------------------通过实盘易申购新股----------------------'''
class Purchase_new_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.times = params.get('times', [[10, 00]])
        self.host = params.get('host', '')
        self.port = params.get('port', 8888)
        self.key = params.get('key', '')
        self.clients = params.get('clients', [])

    def update_params(self, context, params):
        Rule.update_params(self, context, params)
        self.times = params.get('times', [[10, 00]])
        self.host = params.get('host', '')
        self.port = params.get('port', 8888)
        self.key = params.get('key', '')
        self.clients = params.get('clients', [])

    def handle_data(self, context, data):
        hour = context.current_dt.hour
        minute = context.current_dt.minute
        if not [hour, minute] in self.times:
            return
        try:
            import shipane_sdk
        except:
            pass
        shipane = shipane_sdk.Client(g.log_type(self.memo), key=self.key, host=self.host, port=self.port,
                                     show_info=False)
        for client_param in self.clients:
            shipane.purchase_new_stocks(client_param)

    def __str__(self):
        return '实盘易申购新股[time: %s host: %s:%d  key: %s client:%s] ' % (
            self.times, self.host, self.port, self.key, self.clients)
            
# '''------------------邮件通知器-----------------'''
class Email_notice(Op_stocks_record):
    def __init__(self, params):
        Op_stocks_record.__init__(self, params)
        self.user = params.get('user', '')
        self.password = params.get('password', '')
        self.tos = params.get('tos', '')
        self.sender_name = params.get('sender', '发送者')
        self.strategy_name = params.get('strategy_name', '策略1')
        self.str_old_portfolio = ''

    def update_params(self, context, params):
        Op_stocks_record.update_params(self, context, params)
        self.user = params.get('user', '')
        self.password = params.get('password', '')
        self.tos = params.get('tos', '')
        self.sender_name = params.get('sender', '发送者')
        self.strategy_name = params.get('strategy_name', '策略1')
        self.str_old_portfolio = ''
        try:
            Op_stocks_record.update_params(self, context, params)
        except:
            pass

    def before_adjust_start(self, context, data):
        Op_stocks_record.before_trading_start(self, context)
        self.str_old_portfolio = self.__get_portfolio_info_html(context)
        pass

    def after_adjust_end(self, context, data):
        Op_stocks_record.after_adjust_end(self, context, data)
        try:
            send_time = self._params.get('send_time', [])
        except:
            send_time = []
        if self._params.get('send_with_change', True) and not self.position_has_change:
            return
        if len(send_time) == 0 or [context.current_dt.hour, context.current_dt.minute] in send_time:
            self.__send_email('%s:调仓结果' % (self.strategy_name)
                              , self.__get_mail_text_before_adjust(context
                                                                   , ''
                                                                   , self.str_old_portfolio
                                                                   , self.op_sell_stocks
                                                                   , self.op_buy_stocks))
            self.position_has_change = False  # 发送完邮件，重置标记

    def after_trading_end(self, context):
        Op_stocks_record.after_trading_end(self, context)
        self.str_old_portfolio = ''

    def on_clear_position(self, context, new_pindexs=[0]):
        # 清仓通知
        self.op_buy_stocks = self.merge_op_list(self.op_buy_stocks)
        self.op_sell_stocks = self.merge_op_list(self.op_sell_stocks)
        if len(self.op_buy_stocks) > 0 or len(self.op_sell_stocks) > 0:
            self.__send_email('%s:清仓' % (self.strategy_name), '已触发清仓')
            self.op_buy_stocks = []
            self.op_sell_stocks = []
        pass

    # 发送邮件 subject 为邮件主题,content为邮件正文(当前默认为文本邮件)
    def __send_email(self, subject, text):
        # # 发送邮件
        username = self.user  # 你的邮箱账号
        password = self.password  # 你的邮箱授权码。一个16位字符串

        sender = '%s<%s>' % (self.sender_name, self.user)

        msg = MIMEText("<pre>" + text + "</pre>", 'html', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['to'] = ';'.join(self.tos)
        msg['from'] = sender  # 自己的邮件地址

        server = smtplib.SMTP_SSL('smtp.qq.com')
        try:
            # server.connect() # ssl无需这条
            server.login(username, password)  # 登陆
            server.sendmail(sender, self.tos, msg.as_string())  # 发送
            self.log.info('邮件发送成功:' + subject)
        except:
            self.log.info('邮件发送失败:' + subject)
        server.quit()  # 结束

    def __get_mail_text_before_adjust(self, context, op_info, str_old_portfolio,
                                      to_sell_stocks, to_buy_stocks):
        # 获取又买又卖的股票，实质为调仓
        mailtext = context.current_dt.strftime("%Y-%m-%d %H:%M:%S")
        if len(self.g.buy_stocks) >= 5:
            mailtext += '<br>选股前5:<br>' + ''.join(['%s<br>' % (show_stock(x)) for x in self.g.buy_stocks[:5]])
            mailtext += '--------------------------------<br>'
        # mailtext += '<br><font color="blue">'+op_info+'</font><br>'
        if len(to_sell_stocks) + len(to_buy_stocks) == 0:
            mailtext += '<br><font size="5" color="red">* 无需调仓! *</font><br>'
            mailtext += '<br>当前持仓:<br>'
        else:
            #             mailtext += '<br>==> 调仓前持仓:<br>'+str_old_portfolio+"<br>==> 执行调仓<br>--------------------------------<br>"
            mailtext += '卖出股票:<br><font color="blue">'
            mailtext += ''.join(['%s %d<br>' % (show_stock(x[0]), x[1]) for x in to_sell_stocks])
            mailtext += '</font>--------------------------------<br>'
            mailtext += '买入股票:<br><font color="red">'
            mailtext += ''.join(['%s %d<br>' % (show_stock(x[0]), x[1]) for x in to_buy_stocks])
            mailtext += '</font>'
            mailtext += '<br>==> 调仓后持仓:<br>'
        mailtext += self.__get_portfolio_info_html(context)
        return mailtext

    def __get_portfolio_info_html(self, context):
        total_values = context.portfolio.positions_value + context.portfolio.cash
        position_str = "--------------------------------<br>"
        position_str += "总市值 : [ %d ]<br>持仓市值: [ %d ]<br>现金   : [ %d ]<br>" % (
            total_values,
            context.portfolio.positions_value, context.portfolio.cash
        )
        position_str += "<table border=\"1\"><tr><th>股票代码</th><th>持仓</th><th>当前价</th><th>盈亏</th><th>持仓比</th></tr>"
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            if position.price - position.avg_cost > 0:
                tr_color = 'red'
            else:
                tr_color = 'green'
            stock_raite = (position.total_amount * position.price) / total_values * 100
            position_str += '<tr style="color:%s"><td> %s </td><td> %d </td><td> %.2f </td><td> %.2f%% </td><td> %.2f%%</td></tr>' % (
                tr_color,
                show_stock(stock),
                position.total_amount, position.price,
                (position.price - position.avg_cost) / position.avg_cost * 100,
                stock_raite
            )

        return position_str + '</table>'

    def __str__(self):
        return '调仓结果邮件通知:[发送人:%s] [接收人:%s]' % (self.sender_name, str(self.tos))
