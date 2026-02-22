import os

import mysql.connector
from mysql.connector import Error

###### IO ##########################
outfile = open("css/screen.css", "w+")


####### PATH TOWARDS THE CLUSTER PAGES HTML FILES #################
cluster_pages_path = "/home/carterrhea/Documents/X-tra_Archive/Lemur/Web/ClusterPages"

clusters = {}
cluster_obsid = {}
try:  # Get data from database
    mySQLconnection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "Lemur_DB"),
        user=os.getenv("DB_USER", "carterrhea"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    # cluster info
    sql_select_Query = "select * from Clusters"
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

# Read in fonts
outfile.write(
    '@font-face { font-family: OpenSans-Regular;src: url("../fonts/OpenSans/OpenSans-Regular.ttf");}\n'
)

# Begin media definition
outfile.write("@media screen and (max-width: 992px) {")
# Definitions for table display on screen
outfile.write(
    "table {\n display: block;  }\n  table > *, table tr, table td, table th {\n     display: block;\n  }\n"
)
outfile.write("table thead {\n display: none;\n  }\n")
outfile.write("table tbody tr {\n    height: auto;\n    padding: 37px 0;\n  }\n")
outfile.write(
    "table tbody tr td {\n    padding-left: 40% !important;\n    margin-bottom: 24px;\n  }\n"
)
outfile.write("table tbody tr td:last-child {\n    margin-bottom: 0;\n  }\n")
outfile.write(
    "table tbody tr td:before {\n    font-family: OpenSans-Regular;\n    font-size: 14px;\n    color: #999999;\n    line-height: 1.2;\n    font-weight: unset;\n   position: absolute;\n    width: 40%;\n    left: 30px;\n    top: 0;\n }\n"
)


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
head_ct = 1
for field_name in field_names[1:]:
    outfile.write("table tbody tr td:nth-child(" + str(head_ct) + "):before {\n")
    outfile.write('content: "' + fields_mapping[field_name] + '"\n')
    outfile.write("}\n")
    head_ct += 1
outfile.write("table tbody tr td:nth-child(" + str(head_ct) + "):before {\n")
outfile.write('content: "Obsid"\n')
outfile.write("}\n")

# End media
outfile.write(
    "@media (max-width: 576px) { \n .container-table100 { \n padding-left: 15px; \n padding-right: 15px;}\n}"
)
