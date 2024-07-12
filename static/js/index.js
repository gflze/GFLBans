let chartOpts = {
    type: "line",
    data: {},
    options: {
        legend: {
            display: true,
            labels: {

            }
        },
        scales: {
            xAxes: [
                {
                    gridLines: {}
                }
            ],
            yAxes: [
                {
                    gridLines: {}
                }
            ]
        }
    }
};

function stupidSort(e1, e2) {
    let e1_dec = e1.split('/');
    let e2_dec = e2.split('/');

    let year1 = parseInt(e1_dec[0])
    let year2 = parseInt(e2_dec[0])

    if (year1 > year2) {
        return 1;
    } else if (year1 < year2) {
        return -1
    }

    let month1 = parseInt(e1_dec[1]);
    let month2 = parseInt(e2_dec[1]);

    if (month1 > month2) {
        return 1;
    } else if (month1 < month2) {
        return -1;
    }

    let day1 = parseInt(e1_dec[2]);
    let day2 = parseInt(e2_dec[2]);

    if (day1 > day2) {
        return 1
    } else if (day1 < day2) {
        return -1
    }

    return 0
}

$(document).ready(function () {
    gbRequest('GET', '/api/v1/statistics/', null).then(resp => {
        if (resp.ok) {
            resp.json().then(decoded => {
                let labels = Object.keys(decoded.history);

                labels.sort(stupidSort);

                chartOpts.data.labels = labels;

                chartOpts.data.datasets = [
                    {
                        label: "Bans",
                        fill: false,
                        backgroundColor: '#f14668',
                        borderColor: '#f14668',
                        data: []
                    }, {
                        label: "Voice Blocks",
                        fill: false,
                        backgroundColor: '#3273dc',
                        borderColor: '#3273dc',
                        data: []
                    }, {
                        label: "Text Blocks",
                        fill: false,
                        backgroundColor: 'purple',
                        borderColor: 'purple',
                        data: []
                    }, {
                        label: "Admin Chat Blocks",
                        fill: false,
                        backgroundColor: 'mediumseagreen',
                        borderColor: 'mediumseagreen',
                        data: []
                    }, {
                        label: "Call Admin Blocks",
                        fill: false,
                        backgroundColor: '#ffdd57',
                        borderColor: '#ffdd57',
                        data: []
                    }, {
                        label: "Warnings",
                        fill: false,
                        backgroundColor: 'orange',
                        borderColor: 'orange',
                        data: []
                    }, {
                        label: "Total",
                        fill: false,
                        backgroundColor: 'hotpink',
                        borderColor: 'hotpink',
                        data: []
                    }
                ];

                for (let i = 0; i < labels.length; i++) {
                    chartOpts.data.datasets[0].data.push(decoded.history[labels[i]].bans);
                    chartOpts.data.datasets[1].data.push(decoded.history[labels[i]].voice_blocks);
                    chartOpts.data.datasets[2].data.push(decoded.history[labels[i]].chat_blocks);
                    chartOpts.data.datasets[3].data.push(decoded.history[labels[i]].admin_chat_blocks);
                    chartOpts.data.datasets[4].data.push(decoded.history[labels[i]].call_admin_blocks);
                    chartOpts.data.datasets[5].data.push(decoded.history[labels[i]].warnings);
                    chartOpts.data.datasets[6].data.push(decoded.history[labels[i]].total);
                }

                if (getMeta('current_theme') !== 'LIGHT') {
                    chartOpts.options.legend.labels.fontColor = '#FFFFFF'
                    chartOpts.options.scales.xAxes[0].gridLines.color = 'rgba(255, 255, 255, 0.1)'
                    chartOpts.options.scales.yAxes[0].gridLines.color = 'rgba(255, 255, 255, 0.1)'
                }

                console.log(chartOpts);

                let ctx = document.getElementById('infractionsChart').getContext('2d')
                window.gbGraph = new Chart(ctx, chartOpts);

                $('#count_total_infractions').text(decoded.total_infractions);
                $('#count_active_infractions').text(decoded.active_infractions);
                $('#count_servers').text(decoded.total_servers);
                $('#count_total_players').text(decoded.online_players);
                $('#count_total_bans').text(decoded.total_bans);
                $('#count_total_gags').text(decoded.total_voice_blocks);
                $('#count_total_mutes').text(decoded.total_chat_blocks);
                $('#count_total_warnings').text(decoded.total_warnings);

                $('.is-loading').removeClass('is-loading')
            });
        } else {
            throw 'Received Non-OK response from the API.';
        }
    }).catch(function (err) {
        console.log(err);
        showError();
    });
})