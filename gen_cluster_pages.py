from jinja2 import Environment, FileSystemLoader
import os
import sys
import mysql.connector
from mysql.connector import Error
import numpy as np

####### PATH TOWARDS THE CLUSTER PAGES HTML FILES #################
cluster_pages_path='/home/carterrhea/Documents/X-tra_Archive/Lemur/Web/ClusterPages'

clusters = {}
cluster_obsid = {}
try: #Get data from database
    mySQLconnection = mysql.connector.connect(host='localhost',
                                              database='Lemur_DB',
                                              user='carterrhea',
                                              password='REDACTED_DB_PASSWORD')
    #cluster info
    sql_select_Query = "select * from Clusters"
    cursor = mySQLconnection .cursor()
    cursor.execute(sql_select_Query)
    num_fields = len(cursor.description)
    field_names = [i[0] for i in cursor.description]
    records = cursor.fetchall()
    #Step through clusters
    for row in records:
        clusters[row[0]] = [row[i+1] for i in range(len(row)-1)]
        #Cluster obsids
        sql_select_Query_id = "select * from Obsids WHERE ClusterNumber=%s"%row[0]
        cursor_id = mySQLconnection .cursor()
        cursor_id.execute(sql_select_Query_id)
        records_id = cursor_id.fetchall()
        cluster_obsid[row[1]] = []
        for row_id in records_id:
            cluster_obsid[row[1]].append(row_id[1])
        cursor_id.close()
    cursor.close()
except Error as e :
    print ("Error while connecting to MySQL", e)
finally:
    #closing database connection.
    if(mySQLconnection .is_connected()):
        mySQLconnection.close()
        print("MySQL connection is closed")



list_of_cluster_names=[]
for cluster in clusters.items():
    list_of_cluster_names.append(cluster[1][0])





################ JINJA 2 PAGE CREATOR ##################



template_path = 'Web/ClusterPages/templates' #path of html template
out_html_page_path = 'Web/ClusterPages' #path of created html pages


root = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(root, template_path)
env = Environment( loader = FileSystemLoader(templates_dir) )
template = env.get_template('Cluster_page_template.html') #name of template html file

for cluster_name in list_of_cluster_names: #loop over all clusters
    #Get obsid info and add to js file
    with open(out_html_page_path+'/js/'+cluster_name+'_obsid.js','w+') as outfile:
        outfile.write("var Obsids = ")
        plt_count = 0
        for obsid_ in cluster_obsid[cluster_name]:
            outfile.write("'<h2 style="+'"color:white"'+' class="FigureHeaders">'+str(obsid_)+"</h2>'+\n")
            outfile.write("'<div class="+'"wrap-table100"'+">'+\n")
            outfile.write("' <div class="+'"table100"'+">'+\n")
            outfile.write("'  <table>   <thead>'+\n")
            outfile.write("'   <tr class="+'"table100-head"'+">'+\n")
            outfile.write("'   <th>CCD IMAGE</th>'+\n")
            outfile.write("'   <th>Background Flare</th>'+\n")
            outfile.write("'   </tr>   </thead>  <tr>'+\n")
            outfile.write("'   <td>     <img src=../Cluster_plots/"+cluster_name+"/"+str(obsid_)+"_ccds.png alt="+'"ccds"'+' width="100%">   '+" </td>'+\n")
            outfile.write("'   <td>     <img src=../Cluster_plots/"+cluster_name+"/Lightcurve.png alt="+'"LightCurve"'+' width="100%">  '+"  </td>'+\n")
            outfile.write("'   </tr>   </table>  </div> </div>'+\n")
        outfile.write("''\n")
        outfile.write("document.write(Obsids);")
    out_html_page_name = '{}.html'.format(cluster_name) #name of pagefile created

    filename = os.path.join(root, out_html_page_path, out_html_page_name) #path+name of cluster page html file
    with open(filename, 'w') as fh: #Writting html pages with accurate cluster name and figure paths
        fh.write(template.render(
        cluster_name = "{}".format(cluster_name),
        Exp_Cor_Img_path = "../Cluster_plots/{}/bkgsub_exp.png".format(cluster_name),
        Back_Cor_Img_path = "../Cluster_plots/{}/bkg_region.png".format(cluster_name),
        Sing_King_Beto_Surg_path ="../Cluster_plots/{}/Single_Beta.png".format(cluster_name),
        Doub_King_Beto_Surg_path ="../Cluster_plots/{}/Double_Beta.png".format(cluster_name),
        Temp_Prof_path ="../Cluster_plots/{}/Temperature_profile.png".format(cluster_name),
        Dens_Prof_path ="../Cluster_plots/{}/Density_profile.png".format(cluster_name),
        Entro_Prof_path ="../Cluster_plots/{}/Entropy_profile.png".format(cluster_name),
        Press_Prof_path = "../Cluster_plots/{}/Pressure_profile.png".format(cluster_name),
        Cool_Temp_Prof_path ="../Cluster_plots/{}/T_Cool_profile.png".format(cluster_name),
        Abund_Prof_path ="../Cluster_plots/{}/Abundance_profile.png".format(cluster_name),
        #CCD_Img_path ="../Cluster_plots/{}/ccds.png".format(cluster_name),
        #Backg_Flare_path = "../Cluster_plots/{}/Lightcurve.png".format(cluster_name),
        cluster_name_obsid_js = "js/{}_obsid.js".format(cluster_name)
            ))
        #Now to write a js file for the variable size obsid files

        #Now add to template
