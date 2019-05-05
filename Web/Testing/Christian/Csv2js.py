###### IO ##########################
outfile = open("Results_table.js",'w')
infile = open("Results.csv","r")
Header = infile.readline().split(',')


####### PATH TOWARDS THE CLUSTER PAGES HTML FILES #################
cluster_pages_path='./Web/Testing/Artificial_results/Cluster_pages'



######## WRITTING ON JS SCRIPT ###########
# Js variable
outfile.write("var full_Table = '")

# begin table
outfile.write('<table id="Analysis_summary">');outfile.write("'+\n")

# column headers
outfile.write("'<th>'+\n")
for Header_name in Header[1:]:
    outfile.write("'<td>"+Header_name.rstrip()+"</td>'+\n")
outfile.write("'</th>'+\n")

# column data
for line in infile:
    row = line.split(",")
    outfile.write("'<tr>'+\n")
    outfile.write("'")
    for i in range(len(row)):
        if i==1:
            outfile.write('<td><a href="Web/Testing/Artificial_results/Cluster_pages/{}.html">%s</a></td>'.format(row[i]) % row[i].rstrip())
        else:
            outfile.write("<td>%s</td>" % row[i].rstrip())
    outfile.write("'+\n")
    outfile.write("'</tr>'+\n")

# end table
outfile.write("'</table>'\n\n")

# JS write
outfile.write("document.write(full_Table);")