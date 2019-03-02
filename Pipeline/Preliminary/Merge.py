'''
Small script to merge objects

INPUTS:
    chandra_dir -- chandra data directory (e.g. '/home/user/Documents/ChandraData/')
    OBSIDS -- list of OBSIDS to merge (e.g. '[11111,22222]')
    reproccesed_dir -- name of reprocessed directory containing event files(e.g. 'repro')
    Merged_Folder -- Name of Folder to be created with merged data (e.g. 'Merged')
    clean -- Boolean to clean files created from 'merge_obs' command (e.g. 'yes')
'''
import os
from ciao_contrib.runtool import *


def merge_objects(Obsids,clean):
    id_string = ''
    id_hyphen = ''
    for obsid in Obsids:
        id_string += obsid+"/repro/acisf"+obsid+"_repro_evt2.fits,"
        id_hyphen += obsid+"-"
    os.system("merge_obs '"+id_string+"' Merged/ cleanup="+clean )
    return None
