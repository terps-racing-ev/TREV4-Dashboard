export default class Gauge{
    constructor(data) {
        this.data = data;

        if (data.box_xywh && data.box_xywh.length === 4) {
            this.x = Number(data.box_xywh[0]);
            this.y = Number(data.box_xywh[1]);
            this.width = Number(data.box_xywh[2]);
            this.height = Number(data.box_xywh[3]);
        } else {
            this.x = 0;
            this.y = 0;
            this.width = 0;
            this.height = 0;
        }

    }  

    contains(px, py) {
        return (
            px >= this.x &&
            px <= this.x + this.width &&
            py >= this.y &&
            py <= this.y + this.height
        );
    }

    draw(ctx) {
        ctx.strokeRect(this.x, this.y, this.width, this.height);
        ctx.fillText(this.data.label, this.x + 5, this.y + 15);
        alert("drew a shape");
    }
}