import Gauge from "./Gauge.js";

var gaugeType = document.getElementById("gauge_type");
var generateBtn = document.getElementById("generate");
var exportBtn = document.getElementById("export");
var addGaugeBtn = document.getElementById("add_gauge");

var canvasHeight = document.getElementById("height");
var canvasWidth = document.getElementById("width");

var canvas = document.getElementById("canvas");
var createGaugeMenu = document.getElementById("define_gauge");

var linearGaugeOptions = document.getElementById("signed_linear_options");

var activeGauges = [];

var ctx = canvas.getContext("2d");

exportBtn.style.display = "none";
canvas.style.display = "none";
createGaugeMenu.style.display = "none";


var exportData = {
    display: {
        width: Number(canvasWidth.value),
        height: Number(canvasHeight.value),
        bg_color: [255, 255, 255]
    },
    gauges: []
};


gaugeType.addEventListener("change", function () {
    if (gaugeType.value == "simple") {
        document.getElementById("gauge_decimals").style.display = "inline";
        document.getElementById("decimals").style.display = "inline";
        linearGaugeOptions.style.display = "none";
    } else {
        document.getElementById("gauge_decimals").style.display = "none";
        document.getElementById("decimals").style.display = "none";
        linearGaugeOptions.style.display = "inline";
    }
});

generateBtn.addEventListener("click", function () {
    exportBtn.style.display = "inline";
    canvas.style.display = "inline";

    canvas.style.width = canvasWidth.value + "px";
    canvas.style.height = canvasHeight.value + "px";
    canvas.style.backgroundColor = `rgb(${exportData.display.bg_color.join(",")})`;

    canvas.width = Number(canvasWidth.value);
    canvas.height = Number(canvasHeight.value);

    createGaugeMenu.style.display = "inline";

    exportData.display.width = Number(canvasWidth.value);
    exportData.display.height = Number(canvasHeight.value);

    gaugeType.dispatchEvent(new Event("change"));
});

addGaugeBtn.addEventListener("click", function () {
    var type = idToGaugeType(gaugeType.value);
    var label = document.getElementById("gauge_label").value;
    var signal = document.getElementById("gauge_signal").value;
    var decimals = document.getElementById("gauge_decimals").value;
    var min = document.getElementById("gauge_min").value;
    var max = document.getElementById("gauge_max").value;

    var x = document.getElementById("gauge_x").value;
    var y = document.getElementById("gauge_y").value;
    var width = document.getElementById("gauge_width").value;
    var height = document.getElementById("gauge_height").value;
    var transform = [x, y, width, height];

    function hexToRgb(hex) {
        return [
            parseInt(hex.substring(1, 3), 16),
            parseInt(hex.substring(3, 5), 16),
            parseInt(hex.substring(5, 7), 16)
        ];
    }

    var boxColor = hexToRgb(document.getElementById("gauge_box_color").value);
    var borderColor = hexToRgb(document.getElementById("gauge_border_color").value);
    var textColor = hexToRgb(document.getElementById("gauge_text_color").value);
    var positiveColor = hexToRgb(document.getElementById("gauge_positive_color").value);
    var negativeColor = hexToRgb(document.getElementById("gauge_negative_color").value);

    var vertical = document.getElementById("gauge_vertical").checked;
    var showValue = document.getElementById("gauge_show_value").checked;

    var toAdd = {
        type: type,
        label: label,
        signal: signal,
        min_val: min,
        max_val: max,
        box_xywh: transform,
        box_color: boxColor,
        border_color: borderColor,
        text_color: textColor
    };

    if (type === "Simple Gauge") {
        toAdd.decimals = Number(decimals);
    } else if (type === "Signed Linear Gauge") {
        toAdd.positive_color = positiveColor;
        toAdd.negative_color = negativeColor;
        toAdd.vertical = vertical;
        toAdd.show_value = showValue;
    }

    activeGauges.push(new Gauge(toAdd));

    refreshGauges();

    exportData.gauges.push(toAdd);
});

canvas.addEventListener("click", function (e) {
    const mousePos = getMousePos(canvas, e);

    for (let gauge of activeGauges) {
        if (gauge.contains(mousePos.x, mousePos.y)) {
            const result = confirm(`Delete "${gauge.data.label}"?`);

            if (result) {
                console.log("deleting gauge");
                activeGauges = activeGauges.filter(g => g !== gauge);
                exportData.gauges = exportData.gauges.filter(g => g !== gauge.data);
                refreshGauges();
            } else {
                console.log("not deleting gauge");
            }
            break;
        }
    }
})

function getMousePos(canvas, event) {
    const rect = canvas.getBoundingClientRect();

    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    return {
        x: (event.clientX - rect.left) * scaleX,
        y: (event.clientY - rect.top) * scaleY
    };
}


function refreshGauges() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = `rgb(${exportData.display.bg_color.join(",")})`;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let gauge of activeGauges) {
        gauge.draw(ctx);
    }
}

// Modify this as you add more gauge types
function idToGaugeType(id) {
    if (id === "simple") return "Simple Gauge";
    else if (id === "signed_linear") return "Signed Linear Gauge";
    else return null;
}

function downloadJSON(data, filename = "data.json") {
    const jsonStr = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    a.href = url;
    a.download = filename;

    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    URL.revokeObjectURL(url);
}

exportBtn.addEventListener("click", function () {
    downloadJSON(exportData, "gauge_config.json");
});
