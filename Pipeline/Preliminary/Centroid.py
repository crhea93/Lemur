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
def source_region_pick(ccd):
    add_window(32,32)
    max_cts = max_counts('ccd'+ccd+'.img')
    cr = read_file('ccd'+ccd+".img")
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3))
    add_image(cr, ["depth", 50, "wcs", "logical"])
    set_image(["threshold", [0,max_cts/25]])
    set_image(["colormap", "heat"])
    x_min = min_coord('ccd'+ccd+".fits",'x'); x_max = max_coord('ccd'+ccd+".fits",'x')
    y_min = min_coord('ccd'+ccd+".fits",'y'); y_max = max_coord('ccd'+ccd+".fits",'y')
    limits(x_min,x_max,y_min,y_max)
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

def merge_region_pick(merged_evt):
    add_window(32,32)
    max_cts = max_counts(merged_evt+'.img')
    cr = read_file(merged_evt+".img")
    img = copy_piximgvals(cr)
    set_piximgvals(cr, gsmooth(img, 3))
    add_image(cr, ["depth", 50, "wcs", "logical"])
    set_image(["threshold", [0,max_cts/25]])
    set_image(["colormap", "heat"])
    x_min = min_coord(merged_evt+".fits",'x'); x_max = max_coord(merged_evt+".fits",'x')
    y_min = min_coord(merged_evt+".fits",'y'); y_max = max_coord(merged_evt+".fits",'y')
    limits(x_min,x_max,y_min,y_max)
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
    dmstat.punlearn()
    dmstat.infile = 'ccd'+ccd_src+'.img'
    dmstat.centroid = True
    dmstat()
    #print(dmstat.out_max_loc.split(','))
    return dmstat.out_max_loc.split(',')[0],dmstat.out_max_loc.split(',')[1]
def basic_centroid(ccd_src):
    #Chose region to search for centroid
    central_coord, radius = source_region_pick(ccd_src)
    #find centroid
    dmstat.punlearn()
    dmstat.infile = 'ccd'+ccd_src+'.img[sky=circle('+str(central_coord[0][0])+','+str(central_coord[1][0])+','+str(radius)+')]'
    dmstat.centroid = True
    dmstat()
    #print(dmstat.out_max_loc.split(','))
    return dmstat.out_max_loc.split(',')[0],dmstat.out_max_loc.split(',')[1]
def merged_centroid(merged_file):
    # Chose region to search for centroid
    central_coord, radius = merge_region_pick(merged_file)
    # find centroid
    dmstat.punlearn()
    dmstat.infile = merged_file+'.img[sky=circle('+str(central_coord[0][0])+','+str(central_coord[1][0])+','+str(radius)+')]'
    dmstat.centroid = True
    dmstat()
    #print(dmstat.out_max_loc.split(','))
    return dmstat.out_max_loc.split(',')[0],dmstat.out_max_loc.split(',')[1]
