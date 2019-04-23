'''
Create window with all ccds
'''

import os
import matplotlib.pyplot as plt
import easygui as gui
import numpy as np
from pycrates import *
from pychips.all import *
from shutil import copyfile
from ciao_contrib.smooth import *
from ciao_contrib.runtool import *
import matplotlib.image as mpimg

from astropy.io import fits
from matplotlib.colors import LogNorm
from astropy.table import Table
from astropy.convolution import Gaussian2DKernel, convolve
#-----------------------------CLASSES----------------------------------#
class AGN:
    '''
    Class to handle potential AGN. We must contain the central point of the AGN
    and its radius. We also will have a boolean to say whether or not we have an
    AGN in the ICM.
    :param active - AGN or no AGN
    :param center - physical coordinates of AGN center
    :param radius - radius in arcseconds
    '''
    def __init__(self,active):
        self.active = active
        self.x_coord = 0
        self.y_coord = 0
        self.radius = 0
    def set_AGN(self,center_x,center_y,radius):
        self.active = True
        self.x_coord = center_x
        self.y_coord = center_y
        self.radius = radius
#--------------------------Auxilary Functions--------------------------#
def max_counts(image):
    '''Maximum counts in image'''
    dmstat.punlearn()
    dmstat.infile = image
    dmstat.centroid = True
    dmstat()
    return int(dmstat.out_max)

def max_coord(image,coord):
    '''Maximum coordinate for image'''
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_max)

def min_coord(image,coord):
    '''Minimum coordinate for image'''
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_min)
#--------------------------Primary Functions--------------------------#
def display_ccds(ccd_list,obsid,Merge=False):
    '''
    Display all CCDS together
    PARAMETERS:
        ccd_list - list of ccd numbers
        obsid - current Chandra observation ID
    '''
    #add_window(32,32)
    #split(2,int(len(ccd_list[obsid])/2)+1)
    if len(ccd_list[obsid])%2 == 0:
        col_num = int(len(ccd_list[obsid])/2)
    else:
        col_num = int((len(ccd_list[obsid])+1)/2)
    f, ax = plt.subplots(2,col_num)
    ccd_count = 0
    full_ccd_list = ['ccd'+i for i in ccd_list[obsid]]
    #Go through each ccd in the list
    for ccd in full_ccd_list:
        if ccd_count < col_num:
            rw = 0
        else:
            rw = 1
        ccd_moded = ccd_count%col_num
        hdu_list = fits.open(ccd+'.fits', memmap=True)
        evt_data = Table(hdu_list[1].data)
        min_x = np.min(evt_data['x'])
        min_y = np.min(evt_data['y'])
        max_x = np.max(evt_data['x'])
        max_y = np.max(evt_data['y'])
        image_data = fits.getdata(ccd+'.img')
        kernel = Gaussian2DKernel(x_stddev=1)
        astropy_conv = convolve(image_data, kernel)
        ax[rw,ccd_moded].imshow(np.arcsinh(astropy_conv)/25, cmap='gray')
        ax[rw,ccd_moded].set_xlim(min_x,max_x)
        ax[rw,ccd_moded].set_ylim(min_y,max_y)
        ax[rw,ccd_moded].text(min_x,min_y,ccd,fontsize=15,color='white')
        ax[rw,ccd_moded].set_axis_off()
        '''max_cts = max_counts(ccd+'.img')
        #read and plot data after smoothing
        cr = read_file(ccd+".img")
        current_plot("plot"+str(ccd_count))
        img = copy_piximgvals(cr)
        set_piximgvals(cr, gsmooth(img, 3))
        pvalues = get_piximgvals(cr)
        add_image(np.arcsinh(pvalues))
        set_image(["threshold", [0, np.max(np.arcsinh(pvalues))]])
        set_image(["colormap", "heat"])
        x_min = min_coord(ccd+".fits",'x'); x_max = max_coord(ccd+".fits",'x')
        y_min = min_coord(ccd+".fits",'y'); y_max = max_coord(ccd+".fits",'y')
        limits(x_min,x_max,y_min,y_max)
        add_label(x_min, y_min, ccd, ["size", 18])
        set_label(["color", "white"])'''
        ccd_count += 1
        #hide_axis()
    #hide_axis()
    f.subplots_adjust(hspace=0)
    outfile_name = "ccds.png"
    plt.savefig(outfile_name)
    plt.imshow(mpimg.imread('ccds.png')); plt.ion(); plt.show()
    msg = "Which CCD should be used for Background Flare Extraction?"
    bkg_ccd = gui.buttonbox(msg, choices=full_ccd_list)
    if Merge == False:
        msg = "Which CCD should be used for Source Centroid Extraction?"
        src_ccd = gui.buttonbox(msg, choices=full_ccd_list)
        plt.close()
        return bkg_ccd,src_ccd
    else:
        plt.close()
        return bkg_ccd






def display_entire(home_dir,OBSID,repro_evt):
    '''
    Display normal image from reprocessed Chandra data
    PARAMETERS:
        home_dir - directory containing Chandra data
        OBSID - current Chandra observation ID
        repro_evt - name of the reprocessed event
    '''
    os.chdir(home_dir+'/'+OBSID+'/repro')
    point_srcs = True
    repro_img = repro_evt.split('.')[0]+'.img'
    #create image file for reprocessed event
    dmcopy.punlearn()
    dmcopy.infile = repro_evt
    dmcopy.outfile = repro_img
    dmcopy.option = 'image'
    dmcopy.clobber = True
    dmcopy()
    #plot image file
    add_window(32,32)
    max_cts = max_counts(repro_img)
    cr = read_file(repro_img)
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3)) #smooth
    pvalues = get_piximgvals(cr)
    add_image(np.arcsinh(pvalues)) #scale
    set_image(["threshold", [0, np.max(np.arcsinh(pvalues))/10]])
    set_image(["colormap", "heat"])
    x_min = min_coord(repro_evt,'x'); x_max = max_coord(repro_evt,'x')
    y_min = min_coord(repro_evt,'y'); y_max = max_coord(repro_evt,'y')
    limits(x_min,x_max,y_min,y_max)
    #Actively choose diffuse emission
    msg = "Please pick the extent of the diffuse emission..."
    gui.ccbox(msg)
    coords = get_pick()
    #Activily choose background region
    msg = "Please pick the center and edge of background region..."
    gui.ccbox(msg)
    bkg_coord = get_pick()
    #add the points to the image
    add_point(bkg_coord[0], bkg_coord[1], ["style", "cross", "color", "blue"])
    bkg_edge = get_pick()
    add_point(bkg_edge[0], bkg_edge[1], ["style", "cross", "color", "blue"])
    bkg_radius = np.sqrt((float(bkg_coord[0])-float(bkg_edge[0]))**2+(float(bkg_coord[1])-float(bkg_edge[1]))**2)
    #Save the background region
    bkg_file = open('bkg.reg','w+')
    bkg_file.write("# Region file format: DS9 version 4.1 \n")
    bkg_file.write("physical \n")
    bkg_file.write('circle(%s,%s,%f) \n'%(bkg_coord[0][0],bkg_coord[1][0],bkg_radius))
    bkg_file.close()
    #find any point sources contaminating the diffuse emission
    ptsrc_file = open('pt_srcs.reg','w+')
    ptsrc_file.write("# Region file format: DS9 version 4.1 \n")
    ptsrc_file.write("physical \n")
    #Also see if it is the central AGN
    agn_ = AGN(False)
    agn_file = open('AGN.reg','w+')
    agn_file.write("# Region file format: DS9 version 4.1 \n")
    agn_file.write("physical \n")
    while point_srcs == True:
        msg = "Are there any point sources in the src CCD?"
        point_srcs = gui.ynbox(msg)
        if point_srcs == True:
            msg = "Please pick the point source and then the extent of the source after pressing continue..."
            gui.ccbox(msg)
            pt_src_coord = get_pick()
            add_point(pt_src_coord[0], pt_src_coord[1], ["style", "cross", "color", "green"])
            pt_src_edge = get_pick()
            add_point(pt_src_edge[0], pt_src_edge[1], ["style", "cross", "color", "green"])
            radius = np.sqrt((float(pt_src_coord[0])-float(pt_src_edge[0]))**2+(float(pt_src_coord[1])-float(pt_src_edge[1]))**2)
            ptsrc_file.write('circle(%s,%s,%f) \n'%(pt_src_coord[0][0],pt_src_coord[1][0],radius))
            msg = "Is the point src the central AGN?"
            AGN_msg = gui.ynbox(msg)
            if AGN_msg == True:
                agn_file.write('circle(%s,%s,%f) \n'%(pt_src_coord[0][0],pt_src_coord[1][0],radius))
                agn_.set_AGN(pt_src_coord[0][0],pt_src_coord[1][0],radius)
    agn_file.close()
    ptsrc_file.close()
    #move to background directory for later
    copyfile('pt_srcs.reg',home_dir+'/'+OBSID+'/Background/pt_srcs.reg')
    print_window(home_dir+'/'+OBSID+'/bkg.png', ['clobber', 'yes'])
    clear()
    return coords[0][0],coords[1][0],agn_


def display_merge(merged_dir,merged_evt):
    '''
    Display normal image from reprocessed Chandra data after merge
    PARAMETERS:
        merged_dir - directory containing merged Chandra data
        merged_evt - merged event file name
    '''
    os.chdir(merged_dir)
    point_srcs = True
    merged_img = merged_evt.split('.')[0]+'.img'
    #Create merged image
    dmcopy.punlearn()
    dmcopy.infile = merged_evt
    dmcopy.outfile = merged_img
    dmcopy.option = 'image'
    dmcopy.clobber = True
    dmcopy()
    #Plot and such
    add_window(32,32)
    max_cts = max_counts(merged_img)
    cr = read_file(merged_img)
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3)) #smooth
    pvalues = get_piximgvals(cr)
    add_image(np.arcsinh(pvalues)) #scale
    set_image(["threshold", [0, np.arcsinh(np.max(pvalues))]])
    set_image(["colormap", "heat"])
    x_min = min_coord(merged_evt,'x'); x_max = max_coord(merged_evt,'x')
    y_min = min_coord(merged_evt,'y'); y_max = max_coord(merged_evt,'y')
    limits(x_min,x_max,y_min,y_max)
    #Actively choose diffuse emission
    msg = "Please pick the extent of the diffuse emission..."
    gui.ccbox(msg)
    coords = get_pick()
    #add source region to image
    add_point(coords[0], coords[1], ["style", "cross", "color", "red"])
    #Actively choose background region
    msg = "Please pick the center and edge of background region..."
    gui.ccbox(msg)
    bkg_coord = get_pick()
    #add bkg to image
    add_point(bkg_coord[0], bkg_coord[1], ["style", "cross", "color", "blue"])
    bkg_edge = get_pick()
    add_point(bkg_edge[0], bkg_edge[1], ["style", "cross", "color", "blue"])
    bkg_radius = np.sqrt(
        (float(bkg_coord[0]) - float(bkg_edge[0])) ** 2 + (float(bkg_coord[1]) - float(bkg_edge[1])) ** 2)
    #Write background region file
    bkg_file = open('bkg.reg', 'w+')
    bkg_file.write("# Region file format: DS9 version 4.1 \n")
    bkg_file.write("physical \n")
    bkg_file.write('circle(%s,%s,%f) \n' % (bkg_coord[0][0], bkg_coord[1][0], bkg_radius))
    bkg_file.close()
    #check for contaminating pt srcs in diffuse emission and log them
    ptsrc_file = open('pt_srcs.reg','w+')
    ptsrc_file.write("# Region file format: DS9 version 4.1 \n")
    ptsrc_file.write("physical \n")
    #Also see if it is the central AGN
    agn_ = AGN(False)
    agn_file = open('AGN.reg','w+')
    agn_file.write("# Region file format: DS9 version 4.1 \n")
    agn_file.write("physical \n")
    while point_srcs == True:
        msg = "Are there any point sources contaminating the diffuse emission?"
        point_srcs = gui.ynbox(msg)
        if point_srcs == True:
            msg = "Please pick the point source and then the extent of the source after pressing continue..."
            gui.ccbox(msg)
            pt_src_coord = get_pick()
            add_point(pt_src_coord[0], pt_src_coord[1], ["style", "cross", "color", "green"])
            pt_src_edge = get_pick()
            add_point(pt_src_edge[0], pt_src_edge[1], ["style", "cross", "color", "green"])
            radius = np.sqrt((float(pt_src_coord[0])-float(pt_src_edge[0]))**2+(float(pt_src_coord[1])-float(pt_src_edge[1]))**2)
            ptsrc_file.write('annulus(%s,%s,0.0,%f) \n'%(pt_src_coord[0][0],pt_src_coord[1][0],radius))
            msg = "Is the point src the central AGN?"
            AGN_msg = gui.ynbox(msg)
            if AGN_msg == True:
                agn_file.write('circle(%s,%s,%f) \n'%(pt_src_coord[0][0],pt_src_coord[1][0],radius))
                agn_.set_AGN(pt_src_coord[0][0],pt_src_coord[1][0],radius)
    agn_file.close()
    ptsrc_file.close()
    clear()
    return coords[0][0],coords[1][0],agn_
