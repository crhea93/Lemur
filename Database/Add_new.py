'''
Add an entry to the database
'''

def add_cluster_db(mydb,mycursor,cluster_name):
    '''
    Add information to cluster table
    :param mydb:
    :param mycursor:
    :param cluster_name:
    :return:
    '''

    #Check if cluster is already in table
    mycursor.execute(
        "SELECT COUNT(*) FROM Clusters Where Name = %s",
        (cluster_name,)
    )
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        # if the cluster doesnt yet exist
        # Lets get the number of clusters current in set
        mycursor.execute("SELECT COUNT(*) FROM Clusters")
        (number_of_rows_curr,) = mycursor.fetchone()
        sql = "INSERT INTO Clusters (ID,Name,ra) VALUES (%s,%s,%s)"
        val = (number_of_rows_curr,cluster_name, "r2a")
        mycursor.execute(sql, val)
        print("Added cluster to database")
    else:
        #Cluster exists
        sql = "UPDATE Clusters SET Name = %s WHERE Name = %s"
        val = (cluster_name, cluster_name)
        mycursor.execute(sql, val)
        print("Updated cluster")
    mydb.commit()
    return None