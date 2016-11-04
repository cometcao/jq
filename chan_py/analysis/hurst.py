#6 R/S算法计算Hurst
#变量：x-日收益率-list(之后使用np.array变换成数组) 
#输出：计算得到的Hurst值
def hurst(X):
    
    #输入日回报率
    X = np.array(X)
    
    #N代表最大的片段值（即不对X分割时）
    N = X.size
    
    T = np.arange(1, N + 1)
    Y = np.cumsum(X)
    
    #分别计算不同长度的片段的均值
    Ave_T = Y / T

    #每个片段的最大差距R_T
    R_T = np.zeros(N)
    #对应的每段的标准差S_T
    S_T = np.zeros(N)
    
    #分别对不同的大小的切片计算R_T和S_T
    for i in range(N):
        S_T[i] = np.std(X[:i + 1])
        Z_T = Y - T * Ave_T[i]
        R_T[i] = np.ptp(Z_T[:i + 1])
        
    #计算R/S
    R_S = R_T / S_T
    
    #将lg(R/S)作为被解释变量Y
    R_S = np.log(R_S)[1:]
    
    #将lgt作为解释变量X
    n = np.log(T)[1:]
    A = np.column_stack((n, np.ones(n.size)))
    
    #回归得到的斜率即为hurst指数
    [m, c] = np.linalg.lstsq(A, R_S)[0]
    H = m
    return H
