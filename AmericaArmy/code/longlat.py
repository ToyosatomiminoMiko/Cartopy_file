'''
经纬度的度数转换成小数
num经度
lat纬度
E:东经+
W:西经-
N:北纬+
S:南纬-
'''
def ffloat(num):
    s=num[-1]
    if s=='E' or s=='N':
        s=1
    else:
        s=-1
    num1=num[0:-2].split('°')
    try:
        num2=num1[1].split('\'')
    except IndexError:
        pass
    n1=float(num1[0]);n2=float(num2[0]);n3=float(num2[1])
    return s*(n1+n2/60+n3/(60*60))