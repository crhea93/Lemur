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
from crates_contrib.utils import *


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
    if evt2.split('.')[-1] == 'img' or evt2.split('.')[-1] == 'fits':
        dmextract.infile = evt2.split('.')[0]+".img[bin sky="+region+"]"
    else:
        dmextract.infile = evt2+'.img'+"[bin sky="+region+"]"  # OBSID+'_broad_thresh.img'
    dmextract.outfile = 'temp.fits'
    dmextract.clobber = True
    dmextract()
    dmstat.punlearn()
    dmstat.infile = "temp.fits[cols counts]"
    dmstat()
    counts = dmstat.out_mean.split(',')[0]
    return float(counts)


def annuli_obs(home_dir,obsids,cen_ra,cen_dec):
    for obsid in obsids:
        #Change to image coordinates for each obsid
        evt2 = home_dir+'/'+obsid+'/repro/acisf'+obsid+'_repro_evt2_uncontam'
        dmcoords.punlearn()
        dmcoords.infile = evt2 + '.fits'  # OBSID+'_broad_thresh.img'
        dmcoords.option = 'cel'
        dmcoords.ra = cen_ra
        dmcoords.dec = cen_dec
        dmcoords()
        x = dmcoords.x
        y = dmcoords.y
        #Copy annuli into obsid directory
        new_loc = home_dir+'/'+obsid+'/repro/Annuli'
        if os.path.isdir(new_loc):
            shutil.rmtree(new_loc)
        shutil.copytree(os.getcwd()+'/Annuli',new_loc)
        #Update x and y coordinates for specific obsid
        for file in os.listdir(new_loc):
            if file.endswith('.reg'):
                with open(new_loc+'/'+file,'r') as text_file:
                    filedata = text_file.read()
                with open(new_loc + '/' + file, 'r') as text_file:
                    file_line_data = text_file.readlines()
                #Change each annulus x and y coordinates
                x_merg = str(file_line_data[2].split('(')[1].split(',')[0])
                y_merg = str(file_line_data[2].split('(')[1].split(',')[1])
                filedata = filedata.replace(x_merg,str(x))
                filedata = filedata.replace(y_merg,str(y))
                with open(new_loc+'/'+file,'w') as text_file:
                    text_file.write(filedata)
        #Copy the bkg.reg file too
        shutil.copyfile(os.getcwd()+'/bkg.reg',home_dir+'/'+obsid+'/repro/bkg.reg')

    return None

def write_reg(region,num,reg_all):
    with open('Annuli/Annulus_'+str(num)+'.reg','w+') as file:
        file.write("# Region file format: DS9 version 4.1 \n")
        file.write("physical \n")
        file.write(region)
    reg_all.write(region+'\n')
    return None

def create_annuli(main_out,evt2,centrd,edge,num_ann,threshold):
    if not os.path.exists(os.getcwd()+'/Annuli'):
        os.makedirs(os.getcwd()+'/Annuli')
    reg_all = open('Annuli/reg_all.reg','w+')
    reg_all.write("# Region file format: DS9 version 4.1 \n")
    reg_all.write("physical \n")
    #tr = SimpleCoordTransform(evt2+'.img')
    #(r0, d0) = tr.convert("physical", "world", centrd[0], centrd[1])
    dmcoords.punlearn()
    if evt2.split('.')[-1] == 'img' or evt2.split('.')[-1] == 'fits':
        dmcoords.infile = evt2
    else:
        dmcoords.infile = evt2+'.fits'  # OBSID+'_broad_thresh.img'
    dmcoords.option = 'sky'
    dmcoords.x = centrd[0]
    dmcoords.y = centrd[1]
    dmcoords()
    cen_ra = dmcoords.ra; cen_dec = dmcoords.dec
    annuli_num = 0
    annuli_data = dict()
    inner_ann = 0
    max_rad = np.sqrt((float(centrd[0])-float(edge[0]))**2+(float(centrd[1])-float(edge[1]))**2)

    for step in range(num_ann-1):
        new_rad = (step+1)*max_rad/num_ann
        region = 'annulus(%s,%s,%f,%f)'%(centrd[0],centrd[1],inner_ann,new_rad) #FIXME:Need " for radii
        if check_counts(evt2+'.fits',region) > threshold:
            inner_ann = new_rad
            annuli_data[annuli_num] = new_rad
            annuli_num += 1
            write_reg(region,annuli_num,reg_all)
    reg_all.close()
    main_out.write("We have a total of %i annuli" % annuli_num)
    return annuli_data,max_rad,cen_ra,cen_dec


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
    cr = read_file(repro_img)
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3))
    pvalues = get_piximgvals(cr)
    add_image(np.arcsinh(pvalues))
    set_image(["threshold", [0, np.max(np.arcsinh(pvalues))/10]])
    set_image(["colormap", "heat"])
    scale_factor = 10
    #limits(float(centrd[0])-scale_factor*max_rad, float(centrd[0])+scale_factor*max_rad,float(centrd[1])-scale_factor*max_rad,float(centrd[1])+scale_factor*max_rad)
    
    add_region(50,float(centrd[0]),float(centrd[1]),max_rad)
    attrs = {'coordsys': PLOT_NORM}
    attrs['opacity'] = 0.0
    attrs['edge.color'] = 'green'
    print_window(os.getcwd() + '/bkgsub_exp.png', ['clobber', 'yes'])
    clear()
    return None
