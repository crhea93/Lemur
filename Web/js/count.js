var count;
$(document).ready(function() {
		$.ajax({
			type: 'POST',
			url: '../php/count.php',
			data: {},
			success: function (response) {
				//$('#result').html(response);
				count = JSON.parse(response)//JSON.parse(response);
				$('.counter-value').attr("data-count",count);
				document.getElementById("count_result").innerHTML = count;
			}
		});
	//document.getElementById("result").innerHTML = test["redshift"];
});