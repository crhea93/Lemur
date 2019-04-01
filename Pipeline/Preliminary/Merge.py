'''
Small script to merge objects

We are merging the background subtracted images in each obsid because we don't use the newly created evt file since
we only want the image for calculating the centroid, extent of emission, and annuli :)

'''
import os
from ciao_contrib.runtool import *


def merge_objects(Obsids,output_name,clean='yes'):
    id_string = ''
    id_hyphen = ''
    for obsid in Obsids:
        id_string += obsid+"/repro/acisf"+obsid+"_repro_evt2_uncontam.fits,"
        id_hyphen += obsid+"-"
    os.system("merge_obs '"+id_string+"' "+output_name+"/ clobber=yes verbose=0 cleanup="+clean )
    return None
