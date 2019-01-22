'''
Create window with all ccds
'''
from pycrates import *
from pychips.all import *
from ciao_contrib.smooth import *
from ciao_contrib.runtool import *


def max_counts(image):
    dmstat.punlearn()
    dmstat.infile = image+'.img'
    dmstat.centroid = True
    dmstat()
    return int(dmstat.out_max)

def max_coord(image,coord):
    dmstat.punlearn()
    dmstat.infile = image+'.fits[cols '+coord+']'
    dmstat()
    return float(dmstat.out_max)

def min_coord(image,coord):
    dmstat.punlearn()
    dmstat.infile = image+'.fits[cols '+coord+']'
    dmstat()
    return float(dmstat.out_min)

def display_ccds(ccd_list):
    add_window(32,32)
    split(2,int(len(ccd_list)/2)+1)
    ccd_count = 1
    full_ccd_list = ['ccd'+i for i in ccd_list]
    for ccd in full_ccd_list:
        max_cts = max_counts(ccd)
        cr = read_file(ccd+".img")
        current_plot("plot"+str(ccd_count))
        img = copy_piximgvals(cr)
        set_piximgvals(cr, gsmooth(img, 3))
        add_image(cr, ["depth", 50, "wcs", "logical"])
        set_image(["threshold", [0,max_cts/25]])
        set_image(["colormap", "cool"])
        x_min = min_coord(ccd,'x'); x_max = max_coord(ccd,'x')
        y_min = min_coord(ccd,'y'); y_max = max_coord(ccd,'y')
        limits(x_min,x_max,y_min,y_max)
        add_label(x_min, y_min, ccd, ["size", 18])
        set_label(["color", "white"])
        ccd_count += 1
        hide_axis()
    hide_axis()
    outfile_name = "ccds.png"
    print_window(outfile_name,['clobber','yes'])
    return None
