
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

$sql = "SELECT COUNT(*) FROM Clusters";
$result = $conn->query($sql);

if ($result->num_rows > 0) {
    while($row = $result->fetch_assoc()) {
        echo json_encode($row['COUNT(*)']);
        }
} else {
    echo "Couldn't Find Clusters";
}

$conn->close();
