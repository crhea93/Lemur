"""
A simple file to collect all the images we want for the website and move them
to the website directory
"""

import os
import shutil


def plots_to_web(dir, obsids, name, web_dir):
    # Move individual obsid images
    if not os.path.exists(web_dir):
        os.mkdir(web_dir)
    for obsid in obsids:
        os.chdir(dir + "/" + obsid + "/Background")
        if os.path.exists(obsid + "_ccds.png"):
            shutil.copyfile(obsid + "_ccds.png", web_dir + "/" + obsid + "_ccds.png")
        shutil.copyfile(
            obsid + "_Lightcurve.png", web_dir + "/" + obsid + "_Lightcurve.png"
        )
    # Cluster images
    os.chdir(dir + "/" + name)
    if os.path.exists("bkgsub_exp.png"):
        shutil.copyfile("bkgsub_exp.png", web_dir + "/" + "bkgsub_exp.png")
    # Photometric info
    # Beta plots intentionally not published to the web.
    return None
