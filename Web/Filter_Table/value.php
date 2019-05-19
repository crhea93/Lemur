<?php




$servername = "localhost";
$username = "id9499302_carterrhea";
$password = "REDACTED_DB_PASSWORD";
$dbname = "id9499302_lemur_db";

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
//$arr1_err = array();
//$arr2_err = array();

#check if we need to get the errors
if ($search2 == 'csb_flux') {
    $sql2 = "SELECT $search,$search2 FROM csb";
    $result_err1 = $conn->query($sql2);

};

if ($result->num_rows > 0) {
    // output data of each row
    while ($row = $result->fetch_assoc()) {
        array_push($arr1, $row[$search]);
        array_push($arr2, $row[$search2]);
    }
};

if ($result_err1->num_rows > 0) {
    // output data of each row
    while($row2 = $result_err1->fetch_assoc()) {
        array_push($arr1_err,$row2[$search]);
        array_push($arr2_err,$row2[$search2]);

    }
}
else {
    $arr1_err = array_fill(0, $result->num_rows, 0);
    $arr2_err = array_fill(0, $result->num_rows, 0);
};

if ($result->num_rows > 0) {
    echo json_encode(array('Value1'=>$arr1,'Value2'=>$arr2,'err1'=>$arr1_err,'err2'=>$arr2_err));

} else {
    echo "Couldn't Find Cluster";
}
//echo json_encode(array('test'=>$search2));
$conn->close();

