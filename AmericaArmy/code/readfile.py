from longlat import ffloat

with open('baseinfo.txt','r',encoding='utf-8') as f:
    for line in f.readlines():
        l=line.split('\n')[0].split(' ',1)
        if 'N' in l[1]:
            l0=l[1].split('N')
            l0[0]+='N'
        elif 'S' in l[1]:
            l0=l[1].split('S')
            l0[0]+='S'
        #名字，经度，纬度
        name,long,lat=l[0],''.join(l0[0].split(' ')),''.join(l0[1].split(' '))
        print(name,ffloat(long),ffloat(lat))


'''
E:东经+
W:西经-
N:北纬+
S:南纬-
'''