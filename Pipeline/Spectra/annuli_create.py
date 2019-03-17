'''
Create annulus regions used by McDonald et al 2017
'''
import os
import shutil
from pycrates import *
from pychips.all import *
import numpy as np
from ciao_contrib.smooth import *
from ciao_contrib.runtool import *

def max_counts(image):
    dmstat.punlearn()
    dmstat.infile = image
    dmstat.centroid = True
    dmstat()
    return int(dmstat.out_max)

def max_coord(image,coord):
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_max)

def min_coord(image,coord):
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_min)


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


def annuli_obs(home_dir,obsids):
    for obsid in obsids:
        new_loc = home_dir+'/'+obsid+'/repro/Annuli'
        if os.path.isdir(new_loc):
            shutil.rmtree(new_loc)
        shutil.copytree(os.getcwd()+'/Annuli',new_loc)
    return None

def write_reg(evt2,region,num,reg_all):
    with open('Annuli/Annulus_'+str(num)+'.reg','w+') as file:
        file.write("# Region file format: DS9 version 4.1 \n")
        file.write("physical \n")
        file.write(region)
    print(region)
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
    return annuli_data,max_rad


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
    return annuli_data,max_rad

def create_src_img(repro_img,centrd,edge):
    #Be sure that repro_img is the exposure corrected bkg-subtracted one!
    max_rad = np.sqrt((float(centrd[0]) - float(edge[0])) ** 2 + (float(centrd[1]) - float(edge[1])) ** 2)
    add_window(32, 32)
    max_cts = max_counts(repro_img)
    cr = read_file(repro_img)
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3))
    add_image(cr, ["depth", 50, "wcs", "logical"])
    set_image(["threshold", [0, max_cts / 10]])
    set_image(["colormap", "heat"])
    limits(float(centrd[0])-2*max_rad, float(centrd[0])+2*max_rad,float(centrd[1])-2*max_rad,float(centrd[1])+2*max_rad)
    add_region(50,float(centrd[0]),float(centrd[1]),max_rad)
    attrs = {'coordsys': PLOT_NORM}
    attrs['opacity'] = 0.0
    attrs['edge.color'] = 'green'
    print_window(os.getcwd() + '/bkgsub_exp.png', ['clobber', 'yes'])
    clear()
    return None
