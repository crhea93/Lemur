var mysql = require('mysql');

var con = mysql.createConnection({
    host: 'localhost',
    user: 'carterrhea',
    password: 'REDACTED_DB_PASSWORD'
});

con.connect(function(err){
    if (err) throw err;
    console.log("Connected");
    document.getElementByID('connection').innerHTML = 'Connected!';
});
document.getElementById("connection").innerHTML = 'connected yay!';