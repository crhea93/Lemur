'''
Python file to create temperature profile
'''
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from LSCalc import ls_calc
from scipy import interpolate
def profile(data_folder,output_folder,ID,redshift,property,units):
    data_file = pd.read_csv(data_folder+'/annuli_data.csv')
    data = data_file[property]
    min_ = pd.read_csv(data_folder+'/annuli_data_min.csv')
    min_ = min_[property]
    max_ = pd.read_csv(data_folder+'/annuli_data_max.csv')
    max_ = max_[property]
    r_in = data_file['R_in']
    r_out = data_file['R_out']
    regions = []
    arcsec_to_kpc = ls_calc(redshift,1)#arcsec to kpc conversion factor
    for region in range(len(r_in)):
        inner = r_in[region]
        outer = r_out[region]
        mid_point = (inner+outer)/2
        regions.append(mid_point*arcsec_to_kpc)
    err_min = [data[i]-min_[i] for i in range(len(min_))]
    err_max = [max_[i]-data[i] for i in range(len(max_))]
    with open(ID+'.csv','w+') as time_file:
        time_file.write('Radius (kpc), T_cool (Gyr) \n')
        ct = 0
        for region in r_out:
            outer = region*arcsec_to_kpc
            time_file.write(str(outer)+','+str(data[ct])+'\n')
            ct += 1
    #interpolate value
    f = interpolate.UnivariateSpline(regions, data, s=10)
    yToFind = 3
    yreduced = np.array(data) - yToFind
    freduced = interpolate.UnivariateSpline(regions, yreduced, s=0)
    print("T_cool is 3 Gyr at a radius of %.2f kpc"%freduced.roots())
    f = interpolate.UnivariateSpline(regions, min_, s=10)
    yToFind = 3
    yreduced = np.array(min_) - yToFind
    freduced_min = interpolate.UnivariateSpline(regions, yreduced, s=0)
    print("T_cool upper bound is 3 Gyr at a radius of %.2f kpc"%freduced_min.roots())
    f = interpolate.UnivariateSpline(regions, max_, s=10)
    yToFind = 3
    yreduced = np.array(max_) - yToFind
    freduced_max = interpolate.UnivariateSpline(regions, yreduced, s=0)
    print("T_cool lower bound is 3 Gyr at a radius of %.2f kpc"%freduced_max.roots())


    #plot interpolated values
    plt.plot(regions[:10],f(regions[:10]))
    plt.ylabel('T_cool (Gyr)')
    plt.xlabel('R (kpc)')
    plt.title(ID)
    plt.savefig(output_folder+'/T_cool_int.png')
    return freduced.roots(),freduced_min.roots(),freduced_max.roots()

IDS = ['A1068','A1413','A3444','AS780','Ophiuchus','RXCJ1115','RXJ2129']
zs = [0.1375,0.143,0.253,0.256,0.0296,0.354,0.235]
with open('Annabelle.txt','w+') as write_out:
    write_out.write('Name,Redshift,Cooling Radius,Upper Error,Lower Error\n')
    for i in range(len(IDS[1:])):
        ID = IDS[i]
        z = zs[i]
        folder = '/home/carterrhea/Desktop/Annabelle/'+ID+'/'+ID+'/Fits'
        val,min,max = profile(folder,folder,ID,0.253,'T_Cool','years')
        write_out.write('%s,%f,%.2f,%.2f,%.2f\n'%(ID,z,val,max-val,val-min))
