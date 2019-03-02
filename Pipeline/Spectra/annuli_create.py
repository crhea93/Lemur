'''
Create annulus regions used by McDonald et al 2017
'''
import os
import shutil
import numpy as np
from ciao_contrib.runtool import *

def check_counts(evt2,region):
    dmextract.punlearn()
    dmextract.infile = evt2+"[bin sky="+region+"]"
    dmextract.outfile = 'temp.fits'
    dmextract.clobber = True
    dmextract()
    dmstat.punlearn()
    dmstat.infile = "temp.fits[cols counts]"
    dmstat()
    counts = dmstat.out_mean.split(',')[0]
    return float(counts)

def write_reg(evt2,region,num,reg_all):
    with open('Annuli/Annulus_'+str(num)+'.reg','w+') as file:
        file.write("# Region file format: DS9 version 4.1 \n")
        file.write("physical \n")
        file.write(region)
    reg_all.write(region+'\n')
    return None

def create_annuli(curent_dir,evt2,centrd,edge,num_ann,threshold):
    if not os.path.exists(os.getcwd()+'/Annuli'):
        os.makedirs(os.getcwd()+'/Annuli')
    reg_all = open('Annuli/reg_all.reg','w+')
    reg_all.write("# Region file format: DS9 version 4.1 \n")
    reg_all.write("physical \n")
    annuli_num = 0
    annuli_data = dict()
    inner_ann = 0
    max_rad = np.sqrt((float(centrd[0])-float(edge[0]))**2+(float(centrd[1])-float(edge[1]))**2)
    for step in range(num_ann-1):
        new_rad = (step+1)*max_rad/num_ann
        region = 'annulus(%s,%s,%f,%f)'%(centrd[0],centrd[1],inner_ann,new_rad)
        if check_counts(evt2,region) > threshold:
            inner_ann = new_rad
            annuli_data[annuli_num] = new_rad
            annuli_num += 1
            write_reg(evt2,region,annuli_num,reg_all)
    reg_all.close()
    return annuli_data

def create_annuli_preset(curent_dir,evt2,centrd,max_rad,num_ann,threshold):
    if not os.path.exists(os.getcwd()+'/Annuli'):
        os.makedirs(os.getcwd()+'/Annuli')
    reg_all = open('Annuli/reg_all.reg','w+')
    reg_all.write("# Region file format: DS9 version 4.1 \n")
    reg_all.write("physical \n")
    annuli_num = 0
    annuli_data = dict()
    inner_ann = 0
    for step in range(num_ann):
        new_rad = (step+1)*max_rad/num_ann
        region = 'annulus(%s,%s,%f,%f)'%(centrd[0],centrd[1],inner_ann,new_rad)
        if check_counts(evt2,region) > threshold:
            inner_ann = new_rad
            annuli_data[annuli_num] = new_rad
            annuli_num += 1
            write_reg(evt2,region,annuli_num,reg_all)
    reg_all.close()
    return annuli_data
