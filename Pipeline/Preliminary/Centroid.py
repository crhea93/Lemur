'''
Calculate Centroid
'''
import os
from ciao_contrib.runtool import *
def basic_centroid(ccd_src):
    dmstat.punlearn()
    dmstat.infile = 'ccd'+ccd_src+'.img'
    dmstat.centroid = True
    dmstat()
    return dmstat.out_cntrd_phys[0],dmstat.out_cntrd_phys[1]
