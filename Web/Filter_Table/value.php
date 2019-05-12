<?php



$servername = "localhost";
$username = "carterrhea";
$password = "ILoveLuci3!";
$dbname = "Lemur_DB";

// Create connection
$conn = new mysqli($servername, $username, $password, $dbname);
// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}
$search = $_POST['Value1'];
$search2 = $_POST['Value2'];
$sql = "SELECT $search,$search2 FROM Clusters ORDERED BY ClusterName";
$result = $conn->query($sql);

$arr1 = array();
$arr2 = array();
<<<<<<< HEAD
//$arr1_err = array();
//$arr2_err = array();

#check if we need to get the errors
if ($search2 == 'csb_flux') {
    echo 'Searching';
    $sql2 = "SELECT $search,$search2 FROM csb";
    $result_err1 = $conn->query($sql2);
=======
$arr1_err = array();
$arr2_err = array();

#check if we need to get the errors
if ($search == 'csb_ct' || 'csb_pho') {
    $sql = "SELECT $search+'_l',$search2+'_l' FROM csb ORDERED BY ClusterName";
    $result_err1 = $conn->query($sql);
>>>>>>> Website
};

if ($result->num_rows > 0) {
    // output data of each row
    while ($row = $result->fetch_assoc()) {
<<<<<<< HEAD
        array_push($arr1, $row[$search]);
        array_push($arr2, $row[$search2]);
    }
};

if ($result_err1->num_rows > 0) {
    // output data of each row
    echo 'YAY';
    while($row2 = $result_err1->fetch_assoc()) {
        array_push($arr1_err,$row2[$search]);
        array_push($arr2_err,$row2[$search2]);
=======
        #echo "Redshift: " . $row["redshift"]."<br>";
        #$arr= array();
        #$arr['redshift'] = $row['redshift'];
        #$arr['id'] = $row['id'];
        array_push($arr1, $row[$search]);
        array_push($arr2, $row[$search2]);
        #echo json_encode($arr);
        #echo json_encode($row['redshift']);
        //echo json_encode(array('redshift'=>$row['redshift'],'ID'=>$row['ID']));
    }
};

/*if ($result_err1->num_rows > 0) {
    // output data of each row
    while($row = $result_err1->fetch_assoc()) {
        #echo "Redshift: " . $row["redshift"]."<br>";
        #$arr= array();
        #$arr['redshift'] = $row['redshift'];
        #$arr['id'] = $row['id'];
        array_push($arr1_err,$row[$search+'_l']);
        array_push($arr2_err,$row[$search2+"_l"]);
        #echo json_encode($arr);
        #echo json_encode($row['redshift']);
        //echo json_encode(array('redshift'=>$row['redshift'],'ID'=>$row['ID']));
>>>>>>> Website
    }
}
else {
    $arr1_err = array_fill(0, $result->num_rows, 0);
    $arr2_err = array_fill(0, $result->num_rows, 0);
<<<<<<< HEAD
};

if ($result->num_rows > 0) {
    echo json_encode(array('Value1'=>$arr1,'Value2'=>$arr2,'err1'=>$arr1_err,'err2'=>$arr2_err));
=======
}*/


if ($result->num_rows > 0) {
    echo json_encode(array('Value1'=>$arr1,'Value2'=>$arr2));//,'err1'=>$arr1_err,'err2'=>$arr2_err));
>>>>>>> Website
} else {
    echo "Couldn't Find Cluster";
}
//echo json_encode(array('test'=>$search2));
$conn->close();

