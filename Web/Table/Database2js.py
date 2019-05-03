import mysql.connector
from mysql.connector import Error
import numpy as np
###### IO ##########################
outfile = open("Results_table.js",'w')


####### PATH TOWARDS THE CLUSTER PAGES HTML FILES #################
cluster_pages_path='/home/carterrhea/Documents/X-tra_Archive/Lemur/Web/ClusterPages'

clusters = {}
cluster_obsid = {}
try: #Get data from database
    mySQLconnection = mysql.connector.connect(host='localhost',
                                              database='carterrhea',
                                              user='carterrhea',
                                              password='ILoveLuci3!')
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


######## WRITTING ON JS SCRIPT ###########
# Js variable
outfile.write("var full_Table = '")

# begin table
outfile.write('<table id="Analysis_summary">');outfile.write("'+\n")

# column headers
outfile.write("'<thead>'+\n"+"'")
outfile.write('<tr class="table100-head">'+"'"+'+\n')
for field_name in field_names[1:]:
    outfile.write("'<th>"+field_name+"</th>'+\n")
outfile.write("'<th>Obsids</th>'+\n")
outfile.write("'</tr>'"+'+\n')
outfile.write("'</thead>'+\n")
# column data

for cluster in clusters:
    cluster_name = str(clusters[cluster][0])
    obsids = ''
    for obsid  in cluster_obsid[cluster_name]:
        obsids += str(obsid)+','
    #Add in column data
    row = clusters[cluster]
    outfile.write("'<tr>'+\n")
    outfile.write("'")
    for i in range(len(row)):
        if i==0:
            outfile.write('<td class="column0"><a href="../ClusterPages/{}.html" target="_blank">%s</a></td>'.format(row[i]) % row[i])
        else:
            outfile.write('<td class="column0">%s</td>' % row[i])

    outfile.write('<td class="column0">%s</td>' %(obsids[:-1]))
    outfile.write("'+\n")
    outfile.write("'</tr>'+\n")

    #Make individual page
    images_list = ['bkgsub_exp','bkg_region']
    photo_plots = ['Single_Beta','Double_Beta']
    spec_plots = ['Temperature','Density','Entropy','Pressure','T_Cool','Abundance']
    obsid_images = ['ccds','Lightcurve']
    print(cluster_name)
    with open(cluster_pages_path+'/'+cluster_name+'.html','w+') as cluster_page:
        cluster_page.write('<!DOCTYPE html>\n <html lang="en">\n <head>\n<link rel="stylesheet" type="text/css" href="cluster.css">\n<meta charset="UTF-8">'
                           '    <link rel="stylesheet" type="text/css" href="//fonts.googleapis.com/css?family=Ubuntu" />\n'
                           '<link rel="stylesheet" href="https://www.w3schools.com/w3css/4/w3.css">'
                           '\n <title>'+cluster_name+'</title>\n </head> \n <body>\n')
        cluster_page.write('<h1>'+cluster_name+'</h1> \n')
        cluster_page.write('<div class="w3-center"> \n')
        cluster_page.write('  <button class="w3-button w3-round-large w3-teal w3-hover-purple"><a href="#images">Images</a></button> &nbsp; \n')
        cluster_page.write('  <button class="w3-button w3-round-large w3-teal w3-hover-purple"><a href="#spec">Spectroscopic</a></button> &nbsp; \n')
        cluster_page.write('  <button class="w3-button w3-round-large w3-teal w3-hover-purple"><a href="#photo">Photometric</a></button> \n')
        cluster_page.write('  <button class="w3-button w3-round-large w3-teal w3-hover-purple"><a href="#obsid_images">Individual Observations</a></button> \n')
        cluster_page.write('</div> \n ')
        #Images
        plt_count = 0
        cluster_page.write('<h2 style="color:white" id="images">Cluster Images</h2>\n')
        cluster_page.write('<div align="left">\n')
        for plot in images_list:
            if plt_count%2 == 0:
                cluster_page.write('  <div class="row">\n')
            cluster_page.write('    <div class="column"> \n')
            cluster_page.write('      <img src="../Cluster_plots/'+cluster_name+'/'+plot+'.png" alt="'+plot+'Profile"> \n')
            cluster_page.write('    </div> \n')
            if plt_count%2 == 1:
                cluster_page.write('  </div> \n')
            plt_count += 1
        if plt_count%2 == 1:
            cluster_page.write('  </div> \n')
        cluster_page.write('</div>\n')
        #Photometric Plots
        plt_count = 0
        cluster_page.write('<h2 style="color:white" id="photo">Photometric Results</h2>\n')
        cluster_page.write('<div align="left">\n')
        for plot in photo_plots:
            if plt_count%2 == 0:
                cluster_page.write('  <div class="row">\n')
            cluster_page.write('    <div class="column"> \n')
            cluster_page.write('      <img src="../Cluster_plots/'+cluster_name+'/'+plot+'.png" alt="'+plot+'Profile"> \n')
            cluster_page.write('    </div> \n')
            if plt_count%2 == 1:
                cluster_page.write('  </div> \n')
            plt_count += 1
        if plt_count%2 == 1:
            cluster_page.write('  </div> \n')
        cluster_page.write('</div>\n')
        #Spectroscopic Plots
        plt_count = 0
        cluster_page.write('<h2 style="color:white" id="spec">Spectroscopic Results</h2>\n')
        cluster_page.write('<div align="left" id="spec">\n')
        for plot in spec_plots:
            if plt_count%2 == 0:
                cluster_page.write('  <div class="row">\n')
            cluster_page.write('    <div class="column"> \n')
            cluster_page.write('      <img src="../Cluster_plots/'+cluster_name+'/'+plot+'_profile.png" alt="'+plot+'Profile"> \n')
            cluster_page.write('    </div> \n')
            if plt_count%2 == 1:
                cluster_page.write('  </div> \n')
            plt_count += 1
        if plt_count%2 == 1:
            cluster_page.write('  </div> \n')
        cluster_page.write('</div>\n')
        #OBSID IMAGES
        plt_count = 0
        cluster_page.write('<h2 style="color:white" id="obsid">OBSID Images</h2>\n')
        cluster_page.write('<div align="left">\n')
        for obsid_ in cluster_obsid[cluster_name]:
            cluster_page.write('<h3 style="color:white">'+str(obsid_)+'</h3>')
            for plot in obsid_images:
                if plt_count%2 == 0:
                    cluster_page.write('  <div class="row">\n')
                cluster_page.write('    <div class="column"> \n')
                cluster_page.write('      <img src="../Cluster_plots/'+cluster_name+'/'+plot+'.png" alt="'+plot+'"> \n')
                cluster_page.write('    </div> \n')
                if plt_count%2 == 1:
                    cluster_page.write('  </div> \n')
                plt_count += 1
            if plt_count%2 == 1:
                cluster_page.write('  </div> \n')
        cluster_page.write('</div>\n')
# end table
outfile.write("'</table>'\n\n")

# JS write
outfile.write("document.write(full_Table);")
