var gaugeType = document.getElementById("gauge_type");
var generateBtn = document.getElementById("generate");
var exportBtn = document.getElementById("export");
var addGaugeBtn = document.getElementById("add_gauge");

var canvasHeight = document.getElementById("height");
var canvasWidth = document.getElementById("width");

var canvas = document.getElementById("canvas");
var createGaugeMenu = document.getElementById("define_gauge");

var linearGaugeOptions = document.getElementById("signed_linear_options");

document.addEventListener("DOMContentLoaded", function() {
    exportBtn.style.display = "none";
    canvas.style.display = "none";
    createGaugeMenu.style.display = "none";
})

var exportData = {
    display: {
        width: Number(canvasWidth.value),
        height: Number(canvasHeight.value),
        bg_color: [0, 100, 0]
    },
    gauges: []
};

gaugeType.addEventListener("change", function() {
    if(gaugeType.value == "simple"){
        document.getElementById("gauge_decimals").style.display = "inline";
        document.getElementById("decimals").style.display = "inline";    
        linearGaugeOptions.style.display = "none";
    }
    else{
        document.getElementById("gauge_decimals").style.display = "none";
        document.getElementById("decimals").style.display = "none";
        linearGaugeOptions.style.display = "inline";
    }
        
})

generateBtn.addEventListener("click", function() {
    exportBtn.style.display = "inline";
    canvas.style.display = "inline";
    canvas.style.width = canvasWidth.value + "px";
    canvas.style.height = canvasHeight.value + "px";
    createGaugeMenu.style.display = "inline";

    exportData.display.width = Number(canvasWidth.value);
    exportData.display.height = Number(canvasHeight.value);

    gaugeType.dispatchEvent(new Event("change"));

})

addGaugeBtn.addEventListener("click", function() {
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

    var boxCol = document.getElementById("gauge_box_color").value;
    var boxColor = [parseInt(boxCol.substring(1,3), 16), parseInt(boxCol.substring(3,5), 16), parseInt(boxCol.substring(5,7), 16)];

    var borderCol = document.getElementById("gauge_border_color").value;
    var borderColor = [parseInt(borderCol.substring(1,3), 16), parseInt(borderCol.substring(3,5), 16), parseInt(borderCol.substring(5,7), 16)];

    var textCol = document.getElementById("gauge_text_color").value;
    var textColor = [parseInt(textCol.substring(1,3), 16), parseInt(textCol.substring(3,5), 16), parseInt(textCol.substring(5,7), 16)];

    var posCol = document.getElementById("gauge_positive_color").value;
    var positiveColor = [parseInt(posCol.substring(1,3), 16), parseInt(posCol.substring(3,5), 16), parseInt(posCol.substring(5,7), 16)];
    
    var negCol = document.getElementById("gauge_negative_color").value;
    var negativeColor = [parseInt(negCol.substring(1,3), 16), parseInt(negCol.substring(3,5), 16), parseInt(negCol.substring(5,7), 16)];

    var vertical = document.getElementById("gauge_vertical").checked;
    var showValue = document.getElementById("gauge_show_value").checked;

    var toAdd = {
        "type": type,
        "label": label,
        "signal": signal,
        "min_val": min,
        "max_val": max,
        "box_xywh": transform,
        "box_color": boxColor,
        "border_color": borderColor,
        "text_color": textColor
    }

    if(type === "Simple Gauge"){
        toAdd.decimals = Number(decimals);
    } else if (type === "Signed Linear Gauge"){
        toAdd.positive_color = positiveColor;
        toAdd.negative_color = negativeColor;
        toAdd.vertical = vertical;
        toAdd.show_value = showValue;
    }

    exportData.gauges.push(toAdd);
    
})

//modfiy ts as you add more gauge types
function idToGaugeType(id){
    if(id === "simple")
        return "Simple Gauge";
    else if(id === "signed_linear")
        return "Signed Linear Gauge";
    else return null;
}

//tahnk you chatgpt for this glorious function
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

exportBtn.addEventListener("click", function() {

    downloadJSON(exportData, "gauge_config.json");
})