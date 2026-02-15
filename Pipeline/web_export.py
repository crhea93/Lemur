from Misc.PlotToWeb import plots_to_web


def export_web(inputs):
    plots_to_web(
        inputs["home_dir"],
        inputs["dir_list"],
        inputs["name"],
        inputs["web_dir"] + "/" + inputs["name"],
    )
