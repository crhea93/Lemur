function Plot (response, Value1, Value2) {
    //$('#result').html(response);
    test = JSON.parse(response)//JSON.parse(response);
    var trace1 = {
        x: test[Value1],
        y: test[Value2],
        mode: 'markers'
    };
    var data = [trace1];
    var layout = {
        title: {
            //text:'Plot Title',
            font: {
                family: 'Ubuntu, monospace',
                size: 24
            },
            xref: 'paper',
            x: 0.5, //center title
        },
        xaxis: {
            title: {
                text: name1,
                font: {
                    family: 'Ubuntu, monospace',
                    size: 18,
                    color: '#7f7f7f'
                }
            },
        },
        yaxis: {
            title: {
                text: name2,
                font: {
                    family: 'Ubuntu, monospace',
                    size: 18,
                    color: '#7f7f7f'
                }
            }
        }
    };
    Plotly.newPlot('plot_result', data, layout, {showSendToCloud: true});
}