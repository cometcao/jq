#6 R/S�㷨����Hurst
#������x-��������-list(֮��ʹ��np.array�任������) 
#���������õ���Hurstֵ
def hurst(X):
    
    #�����ջر���
    X = np.array(X)
    
    #N��������Ƭ��ֵ��������X�ָ�ʱ��
    N = X.size
    
    T = np.arange(1, N + 1)
    Y = np.cumsum(X)
    
    #�ֱ���㲻ͬ���ȵ�Ƭ�εľ�ֵ
    Ave_T = Y / T

    #ÿ��Ƭ�ε������R_T
    R_T = np.zeros(N)
    #��Ӧ��ÿ�εı�׼��S_T
    S_T = np.zeros(N)
    
    #�ֱ�Բ�ͬ�Ĵ�С����Ƭ����R_T��S_T
    for i in range(N):
        S_T[i] = np.std(X[:i + 1])
        Z_T = Y - T * Ave_T[i]
        R_T[i] = np.ptp(Z_T[:i + 1])
        
    #����R/S
    R_S = R_T / S_T
    
    #��lg(R/S)��Ϊ�����ͱ���Y
    R_S = np.log(R_S)[1:]
    
    #��lgt��Ϊ���ͱ���X
    n = np.log(T)[1:]
    A = np.column_stack((n, np.ones(n.size)))
    
    #�ع�õ���б�ʼ�Ϊhurstָ��
    [m, c] = np.linalg.lstsq(A, R_S)[0]
    H = m
    return H
