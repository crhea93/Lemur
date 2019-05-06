'''
Calculate Centroid
'''
import os
import numpy as np
import easygui as gui
from ciao_contrib.runtool import *
from pycrates import *
from pychips.all import *
from ciao_contrib.smooth import *

def max_counts(image):
    '''Maximum counts in an image'''
    dmstat.punlearn()
    dmstat.infile = image
    dmstat.centroid = True
    dmstat()
    return int(dmstat.out_max)

def max_coord(image,coord):
    '''Maximum coordinate value in an image'''
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_max)

def min_coord(image,coord):
    '''Minimum coordinate value in an image'''
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_min)
def source_region_pick(ccd):
    '''
    Determination of visual centroid for calculation of X-ray centroid
    PARAMETERS:
        ccd - ccd containing source
    '''
    add_window(32,32)
    #Just getting important info for plot and plotting
    max_cts = max_counts(ccd+'.img')
    cr = read_file(ccd+".img")
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3))
    add_image(cr, ["depth", 50, "wcs", "logical"])
    set_image(["threshold", [0,max_cts]])
    set_image(["colormap", "heat"])
    x_min = min_coord(ccd+".fits",'x'); x_max = max_coord(ccd+".fits",'x')
    y_min = min_coord(ccd+".fits",'y'); y_max = max_coord(ccd+".fits",'y')
    limits(x_min,x_max,y_min,y_max)
    #Choose visual centroid
    msg = "Please choose the visual centroid and a small region about the centroid not containing any additional point sources..."
    gui.ccbox(msg)
    central_coord = get_pick()
    #Adding to plot
    add_point(central_coord[0], central_coord[1], ["style", "cross", "color", "green"])
    central_edge = get_pick()
    add_point(central_edge[0], central_edge[1], ["style", "cross", "color", "green"])
    hide_axis()
    hide_point("all")
    radius = np.sqrt((float(central_coord[0]) - float(central_edge[0])) ** 2 + (float(central_coord[1]) - float(central_edge[1])) ** 2)
    #Plotting and saving data
    add_region(50,float(central_coord[0]),float(central_coord[1]),radius)
    attrs = {'coordsys': PLOT_NORM}
    attrs['opacity'] = 0.0
    attrs['edge.color'] = 'green'
    outfile_name = "central.png"
    print_window(outfile_name,['clobber','yes'])

    clear()
    return central_coord,radius

def merge_region_pick(merged_evt):
    '''
    Choosing visual centroid for merged data
    PARAMETERS:
        merged_evt - event file for merged observations
    '''
    add_window(32,32)
    #max_cts = max_counts(merged_evt)
    cr = read_file(merged_evt)
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3)) #smooth
    pvalues = get_piximgvals(cr)
    add_image(np.arcsinh(pvalues)) #scale
    set_image(["threshold", [0, np.max(np.arcsinh(pvalues))]])
    set_image(["colormap", "heat"])
    msg = "Please choose the visual centroid and a small region about the centroid not containing any additional point sources..."
    gui.ccbox(msg)
    central_coord = get_pick()
    add_point(central_coord[0], central_coord[1], ["style", "cross", "color", "green"])
    central_edge = get_pick()
    add_point(central_edge[0], central_edge[1], ["style", "cross", "color", "green"])
    hide_axis()
    outfile_name = "central.png"
    print_window(outfile_name,['clobber','yes'])
    radius = np.sqrt((float(central_coord[0]) - float(central_edge[0])) ** 2 + (float(central_coord[1]) - float(central_edge[1])) ** 2)
    clear()
    return central_coord,radius


def basic_centroid_guess(ccd_src):
    '''
    Initial Guess of the X-ray centroid
    PARAMETERS:
        ccd_src - CCD number that contains source
    '''
    dmstat.punlearn()
    dmstat.infile = ccd_src+'.img'
    dmstat.centroid = True
    dmstat()
    #print(dmstat.out_max_loc.split(','))
    return dmstat.out_max_loc.split(',')[0],dmstat.out_max_loc.split(',')[1]
def basic_centroid(ccd_src):
    '''
    Final choice of centroid
    PARAMETERS:
        ccd_src - CCD number that contains source
    '''
    #Chose region to search for centroid
    central_coord, radius = source_region_pick(ccd_src)
    #find centroid
    dmstat.punlearn()
    dmstat.infile = ccd_src+'.img[sky=circle('+str(central_coord[0][0])+','+str(central_coord[1][0])+','+str(radius)+')]'
    dmstat.centroid = True
    dmstat()
    #print(dmstat.out_max_loc.split(','))
    return dmstat.out_max_loc.split(',')[0],dmstat.out_max_loc.split(',')[1]
def merged_centroid(merged_img):
    '''
    Final choice of centroid in merged observations
    PARAMETERS:
        merged_file - img file for merged observations without extensions
    OUTPUT IN PHYSICAL UNITS
    '''

    central_coord, radius = merge_region_pick(merged_img)
    #Change ra dec to physical coordinates for center
    dmcoords.punlearn()
    dmcoords.infile = merged_img#OBSID+'_broad_thresh.img'
    dmcoords.option = 'logical'
    dmcoords.logicalx = central_coord[0][0]
    dmcoords.logicaly = central_coord[1][0]
    dmcoords()
    cen_x = dmcoords.ra
    cen_y = dmcoords.dec
    # find centroid
    dmstat.punlearn()
    dmstat.infile = merged_img+'[sky=circle('+str(cen_x)+','+str(cen_y)+','+str(radius)+')]'
    dmstat.centroid = True
    dmstat()
    #print(dmstat.out_max_loc.split(','))
    #Coordinates in Physical units
    return dmstat.out_max_loc.split(',')[0],dmstat.out_max_loc.split(',')[1]
