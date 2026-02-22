import os

import mysql.connector
from mysql.connector import Error

###### IO ##########################
outfile = open("Results_table.js", "w")


####### PATH TOWARDS THE CLUSTER PAGES HTML FILES #################
cluster_pages_path = "/home/carterrhea/Documents/X-tra_Archive/Lemur/Web/ClusterPages"

clusters = {}
cluster_obsid = {}
try:  # Get data from database
    mySQLconnection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "carterrhea"),
        user=os.getenv("DB_USER", "carterrhea"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    # cluster info
    sql_select_Query = "select * from Clusters ORDER BY Name"
    cursor = mySQLconnection.cursor()
    cursor.execute(sql_select_Query)
    num_fields = len(cursor.description)
    field_names = [i[0] for i in cursor.description]
    records = cursor.fetchall()
    # Step through clusters
    for row in records:
        clusters[row[0]] = [row[i + 1] for i in range(len(row) - 1)]
        # Cluster obsids
        sql_select_Query_id = "select * from Obsids WHERE ClusterNumber=%s" % row[0]
        cursor_id = mySQLconnection.cursor()
        cursor_id.execute(sql_select_Query_id)
        records_id = cursor_id.fetchall()
        cluster_obsid[row[1]] = []
        for row_id in records_id:
            cluster_obsid[row[1]].append(row_id[1])
        cursor_id.close()
    cursor.close()
except Error as e:
    print("Error while connecting to MySQL", e)
finally:
    # closing database connection.
    if mySQLconnection.is_connected():
        mySQLconnection.close()
        print("MySQL connection is closed")


######## WRITTING ON JS SCRIPT ###########
# Js variable
outfile.write("var full_Table = '")

# begin table
outfile.write('<table id="Analysis_summary">')
outfile.write("'+\n")

# column headers
fields_mapping = {
    "Name": "Cluster Name",
    "redshift": "Redshift",
    "RightAsc": "Right Ascension",
    "Declination": "Declination",
    "R_cool_3": "Cooling Radius at 3 Gyr",
    "R_cool_7": "Cooling Radius at 7.7 Gyr",
    "csb_ct": "Coefficient (ct/s)",
    "csb_pho": "Coefficient (ph/cm^2/s)",
    "csb_flux": "Coefficient (ergs/cm^2/s)",
}
outfile.write("'<thead>'+\n" + "'")
outfile.write('<tr class="table100-head">' + "'" + "+\n")
for field_name in field_names[1:]:  # Skip ID -> not necessary here
    outfile.write("'<th>" + fields_mapping[field_name] + "</th>'+\n")
outfile.write("'<th>Obsids</th>'+\n")
outfile.write("'</tr>'" + "+\n")
outfile.write("'</thead>'+\n")
# column data

for cluster in clusters:
    cluster_name = str(clusters[cluster][0])
    obsids = ""
    for obsid in cluster_obsid[cluster_name]:
        obsids += str(obsid) + ","
    # Add in column data
    row = clusters[cluster]
    outfile.write("'<tr>'+\n")
    outfile.write("'")
    for i in range(len(row)):
        if i == 0:
            outfile.write(
                '<td class="column0"><a href="../ClusterPages/{}.html" target="_blank">%s</a></td>'.format(
                    row[i]
                )
                % row[i]
            )
        else:
            outfile.write('<td class="column0">%s</td>' % row[i])

    outfile.write('<td class="column0">%s</td>' % (obsids[:-1]))
    outfile.write("'+\n")
    outfile.write("'</tr>'+\n")

outfile.write("'</table>'\n\n")

# JS write
outfile.write("document.write(full_Table);")
