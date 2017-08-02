'''
Created on 2 Aug 2017

@author: MetalInvest
'''

class drawKChart(object):
    '''
    This class is used to draw out the K chart
    '''

    def __init__(self):
        '''
        Constructor
        '''
        
    def showInteractiveDf(self, quotes):    
        import time
        from math import pi
        import pandas as pd
        from bokeh.io import output_notebook
        from bokeh.plotting import figure, show
        from bokeh.models import ColumnDataSource, Rect, HoverTool, Range1d, LinearAxis, WheelZoomTool, PanTool, ResetTool, ResizeTool, PreviewSaveTool       
        output_notebook()
        quotes[quotes['volume']==0]=np.nan
        quotes= quotes.dropna()
        openp=quotes['open']
        closep=quotes['close']
        highp=quotes['high']
        lowp=quotes['low']
        volume=quotes['volume']
        time=quotes.index
        date=[x.strftime("%Y-%m-%d") for x in quotes.index]
        quotes['date']=date
        
        w = 12*60*60*1000 # half day in ms
        mids = (openp + closep)/2
        spans = abs(closep-openp)
        inc = closep > openp
        dec = openp > closep
        ht = HoverTool(tooltips=[
                    ("date", "@date"),
                    ("open", "@open"),
                    ("close", "@close"),
                    ("high", "@high"),
                    ("low", "@low"),
                    ("volume", "@volume"),
                    ("money", "@money"),])
        TOOLS = [ht, WheelZoomTool(dimensions=['width']), ResizeTool(), ResetTool(),PanTool(dimensions=['width']), PreviewSaveTool()]
        
        max_x = max(highp)
        min_x = min(lowp)
        x_range = max_x - min_x  
        y_range = (min_x - x_range / 2.0, max_x + x_range * 0.1)  
        p = figure(x_axis_type="datetime", tools=TOOLS, plot_height=600, plot_width=950,toolbar_location="above", y_range=y_range)
        
        p.xaxis.major_label_orientation = pi/4
        p.grid.grid_line_alpha=0.3
        p.background_fill = "black"
        
        quotesdate=dict(date1=quotes['date'],open1=openp,close1=closep,high1=highp,low1=lowp)
        ColumnDataSource(quotesdate)
        x_rect_inc_src =ColumnDataSource(quotes[inc])
        x_rect_dec_src =ColumnDataSource(quotes[dec])
        
        p.rect(time[inc], mids[inc], w, spans[inc], fill_color="red", line_color="red", source=x_rect_inc_src)
        p.rect(time[dec], mids[dec], w, spans[dec], fill_color="green", line_color="green", source=x_rect_dec_src)
        p.segment(time[inc], highp[inc], time[inc], lowp[inc], color="red")
        p.segment(time[dec], highp[dec], time[dec], lowp[dec], color="green")
        show(p)
        
    def showDf(self, quotes):
        # chart lib
        import matplotlib as mat
        import numpy as np
        import datetime as dt
        import matplotlib.pyplot as plt
        import time
        ##########        
        # 代码拷贝自https://www.joinquant.com/post/1756
        # 感谢alpha-smart-dog
        quotes[quotes['volume']==0]=np.nan
        quotes= quotes.dropna()
        Close=quotes['close']
        Open=quotes['open']
        High=quotes['high']
        Low=quotes['low']
        T0 = quotes.index.values
        
        length=len(Close)
        
        fig = plt.figure(figsize=(16, 8))
        ax1 = plt.subplot2grid((10,4),(0,0),rowspan=10,colspan=4)
        #fig = plt.figure()
        #ax1 = plt.axes([0,0,3,2])
        
        X=np.array(range(0, length))
        pad_nan=X+nan
        
            #计算上 下影线
        max_clop=Close.copy()
        max_clop[Close<Open]=Open[Close<Open]
        min_clop=Close.copy()
        min_clop[Close>Open]=Open[Close>Open]
        
            #上影线
        line_up=np.array([High,max_clop,pad_nan])
        line_up=np.ravel(line_up,'F')
            #下影线
        line_down=np.array([Low,min_clop,pad_nan])
        line_down=np.ravel(line_down,'F')
        
            #计算上下影线对应的X坐标
        pad_nan=nan+X
        pad_X=np.array([X,X,X])
        pad_X=np.ravel(pad_X,'F')
        
            #画出实体部分,先画收盘价在上的部分
        up_cl=Close.copy()
        up_cl[Close<=Open]=nan
        up_op=Open.copy()
        up_op[Close<=Open]=nan
        
        down_cl=Close.copy()
        down_cl[Open<=Close]=nan
        down_op=Open.copy()
        down_op[Open<=Close]=nan
        
        even=Close.copy()
        even[Close!=Open]=nan
        
        #画出收红的实体部分
        pad_box_up=np.array([up_op,up_op,up_cl,up_cl,pad_nan])
        pad_box_up=np.ravel(pad_box_up,'F')
        pad_box_down=np.array([down_cl,down_cl,down_op,down_op,pad_nan])
        pad_box_down=np.ravel(pad_box_down,'F')
        pad_box_even=np.array([even,even,even,even,pad_nan])
        pad_box_even=np.ravel(pad_box_even,'F')
        
        #X的nan可以不用与y一一对应
        X_left=X-0.25
        X_right=X+0.25
        box_X=np.array([X_left,X_right,X_right,X_left,pad_nan])
        box_X=np.ravel(box_X,'F')
        
        #Close_handle=plt.plot(pad_X,line_up,color='k') 
        
        vertices_up=array([box_X,pad_box_up]).T
        vertices_down=array([box_X,pad_box_down]).T
        vertices_even=array([box_X,pad_box_even]).T
        
        handle_box_up=mat.patches.Polygon(vertices_up,color='r',zorder=1)
        handle_box_down=mat.patches.Polygon(vertices_down,color='g',zorder=1)
        handle_box_even=mat.patches.Polygon(vertices_even,color='k',zorder=1)
        
        ax1.add_patch(handle_box_up)
        ax1.add_patch(handle_box_down)
        ax1.add_patch(handle_box_even)
        
        handle_line_up=mat.lines.Line2D(pad_X,line_up,color='k',linestyle='solid',zorder=0) 
        handle_line_down=mat.lines.Line2D(pad_X,line_down,color='k',linestyle='solid',zorder=0) 
        
        ax1.add_line(handle_line_up)
        ax1.add_line(handle_line_down)
        
        v=[0,length,Open.min()-0.5,Open.max()+0.5]
        plt.axis(v)
        
        T1 = T0[-len(T0):].astype(dt.date)/1000000000
        Ti=[]
        for i in range(len(T0)/5):
            a=i*5
            d = dt.date.fromtimestamp(T1[a])
            #print d
            T2=d.strftime('$%Y-%m-%d$')
            Ti.append(T2)
            #print tab
        d1= dt.date.fromtimestamp(T1[len(T0)-1])
        d2=d1.strftime('$%Y-%m-%d$')
        Ti.append(d2)
        
        ax1.set_xticks(np.linspace(-2,len(Close)+2,len(Ti))) 
        
        ll=Low.min()*0.97
        hh=High.max()*1.03
        ax1.set_ylim(ll,hh) 
        
        ax1.set_xticklabels(Ti)
        
        plt.grid(True)
        plt.setp(plt.gca().get_xticklabels(), rotation=45, horizontalalignment='right')