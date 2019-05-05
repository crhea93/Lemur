
<?php



$servername = "localhost";
$username = "carterrhea";
$password = "REDACTED_DB_PASSWORD";
$dbname = "Lemur_DB";

// Create connection
$conn = new mysqli($servername, $username, $password, $dbname);
// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}
$search = $_POST['Value1'];
$search2 = $_POST['Value2'];
$sql = "SELECT $search,$search2 FROM Clusters";
$result = $conn->query($sql);

$arr1 = array();
$arr2 = array();
if ($result->num_rows > 0) {
    // output data of each row
    while($row = $result->fetch_assoc()) {
        #echo "Redshift: " . $row["redshift"]."<br>";
        #$arr= array();
        #$arr['redshift'] = $row['redshift'];
        #$arr['id'] = $row['id'];
        array_push($arr1,$row[$search]);
        array_push($arr2,$row[$search2]);
        #echo json_encode($arr);
        #echo json_encode($row['redshift']);
        //echo json_encode(array('redshift'=>$row['redshift'],'ID'=>$row['ID']));
    }
    echo json_encode(array('Value1'=>$arr1,'Value2'=>$arr2));
} else {
    echo "Couldn't Find Cluster";
}
$conn->close();

