"use strict";
function refreshExportRange() {
  const duration=projectDuration(), range=project.exportRange;
  if (!document.getElementById("exportIn")) return;
  document.getElementById("exportIn").value=range?.in ?? 0;
  document.getElementById("exportOut").value=range?.out ?? duration;
  document.getElementById("exportRangeSummary").textContent=range ? `${formatTime(range.in)} → ${formatTime(range.out)} · ${(range.out-range.in).toFixed(2)}s` : t("Full timeline");
  document.getElementById("timelineDurationMode").value=project.timelineDuration ? "custom" : "auto";
  document.getElementById("timelineDurationInput").value=duration;
  document.getElementById("timelineDurationInput").disabled=!project.timelineDuration;
}
function markExportRange(edge,value) {
  const duration=projectDuration(), range={in:0,out:duration,...project.exportRange};
  range[edge]=Math.max(0,Math.min(duration,Number(value)));
  if (!Number.isFinite(range[edge]) || range.out<=range.in) { toast(t("OUT must be after IN."),"error"); refreshExportRange(); return; }
  project.exportRange=range; refreshExportRange(); timeline?.draw(); scheduleSave();
}
function setupExportRange() {
  for (const [edge,name] of [["in","In"],["out","Out"]]) {
    document.getElementById(`markExport${name}`).onclick=()=>markExportRange(edge,currentPlaybackTime());
    document.getElementById(`export${name}`).onchange=e=>markExportRange(edge,e.target.value);
  }
  document.getElementById("clearExportRange").onclick=()=>{delete project.exportRange;refreshExportRange();timeline?.draw();scheduleSave();};
  const changeDuration=value=>{
    if (value!==null && (!Number.isFinite(value)||value<.5)) return refreshExportRange();
    project.timelineDuration=value;
    const duration=projectDuration();
    if (project.exportRange) {
      project.exportRange.out=Math.min(duration,project.exportRange.out);
      if (project.exportRange.in>=project.exportRange.out) delete project.exportRange;
    }
    if (currentPlaybackTime()>duration) seekTo(duration);
    updateDurationUI();timeline?.fitAll();scheduleSave();
  };
  document.getElementById("timelineDurationMode").onchange=e=>changeDuration(e.target.value==="custom" ? projectDuration() : null);
  document.getElementById("timelineDurationInput").onchange=e=>changeDuration(Number(e.target.value));
  document.addEventListener("keydown",e=>{
    if (e.ctrlKey||e.metaKey||e.altKey||e.repeat||e.target.closest("input,textarea,select,[contenteditable=true]")||document.querySelector("dialog[open]")) return;
    const key=e.key.toLowerCase();if(key!=="i"&&key!=="o")return;
    e.preventDefault();markExportRange(key==="i"?"in":"out",currentPlaybackTime());
  });
  let dragEdge=null;
  const canvas=els.timelineCanvas;
  canvas.addEventListener("pointerdown",e=>{
    if(e.button!==0||!project.exportRange||!timeline)return;
    const x=e.clientX-canvas.getBoundingClientRect().left,offset=project.timing.offset||0;
    const distances=["in","out"].map(edge=>[edge,Math.abs(x-timeline.timeToX(project.exportRange[edge]-offset))]);
    distances.sort((a,b)=>a[1]-b[1]);if(distances[0][1]>8)return;
    dragEdge=distances[0][0];e.preventDefault();e.stopImmediatePropagation();canvas.setPointerCapture(e.pointerId);
  },true);
  canvas.addEventListener("pointermove",e=>{
    if(!dragEdge)return;
    e.preventDefault();e.stopImmediatePropagation();
    const range=project.exportRange,minimum=1/(project.canvas.fps||30);
    let value=Math.max(0,Math.min(projectDuration(),timeline.xToTime(e.clientX-canvas.getBoundingClientRect().left)+(project.timing.offset||0)));
    value=dragEdge==="in"?Math.min(value,range.out-minimum):Math.max(value,range.in+minimum);
    if(value<0||value>projectDuration())return;
    range[dragEdge]=value;refreshExportRange();timeline.draw();
  },true);
  const finishDrag=e=>{if(!dragEdge)return;dragEdge=null;e.stopImmediatePropagation();scheduleSave();};
  canvas.addEventListener("pointerup",finishDrag,true);canvas.addEventListener("pointercancel",finishDrag,true);
  refreshExportRange();
}
