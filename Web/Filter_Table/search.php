
<?php

$text2 = $_POST['Name'];


$servername = getenv('DB_HOST') ?: "localhost";
$username = getenv('DB_USER') ?: "";
$password = getenv('DB_PASSWORD') ?: "";
$dbname = getenv('DB_NAME') ?: "Lemur_DB";

// Create connection
$conn = new mysqli($servername, $username, $password, $dbname);
// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}
$search = $_POST['Name'];

$sql = "SELECT * FROM Clusters WHERE Name='$search'";
$result = $conn->query($sql);

$redshifts = array();
$ids = array();
if ($result->num_rows > 0) {
    // output data of each row
    while($row = $result->fetch_assoc()) {
        #echo "Redshift: " . $row["redshift"]."<br>";
        #$arr= array();
        #$arr['redshift'] = $row['redshift'];
        #$arr['id'] = $row['id'];
        array_push($redshifts,$row['redshift']);
        array_push($ids,$row['ID']);
        #echo json_encode($arr);
        #echo json_encode($row['redshift']);
        //echo json_encode(array('redshift'=>$row['redshift'],'ID'=>$row['ID']));
    }
    echo json_encode(array('redshift'=>$redshifts,'ID'=>$ids));
} else {
    echo "Couldn't Find Cluster";
}
$conn->close();
