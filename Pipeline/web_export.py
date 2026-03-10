import os
import shutil


def plots_to_web(dir, obsids, name, web_dir):
    if not os.path.exists(web_dir):
        os.mkdir(web_dir)
    for obsid in obsids:
        os.chdir(dir + "/" + obsid + "/Background")
        if os.path.exists(obsid + "_ccds.png"):
            shutil.copyfile(obsid + "_ccds.png", web_dir + "/" + obsid + "_ccds.png")
        if os.path.exists(obsid + "_Lightcurve.png"):
            shutil.copyfile(
                obsid + "_Lightcurve.png", web_dir + "/" + obsid + "_Lightcurve.png"
            )
    os.chdir(dir + "/" + name)
    if os.path.exists("bkgsub_exp.png"):
        shutil.copyfile("bkgsub_exp.png", web_dir + "/" + "bkgsub_exp.png")


def export_web(inputs):
    plots_to_web(
        inputs["home_dir"],
        inputs["dir_list"],
        inputs["name"],
        inputs["web_dir"] + "/" + inputs["name"],
    )
