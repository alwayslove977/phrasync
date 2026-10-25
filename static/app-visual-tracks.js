"use strict";

function removeBackgroundTrack(index) {
  const bg = project.background, tracks = bg.tracks || ["V1"];
  if (!Number.isInteger(index) || index < 0 || index >= tracks.length) return;
  const used = (bg.clips || []).some(clip => (clip.track || 0) === index);
  if (used && !confirm(t("Remove this track and its clips? Original media stays in the bin."))) return;
  bg.clips = (bg.clips || []).filter(clip => (clip.track || 0) !== index);
  for (const clip of bg.clips) if ((clip.track || 0) > index) clip.track -= 1;
  bg.tracks = tracks.filter((_,i) => i !== index).map((_,i) => `V${i+1}`);
  if (!bg.tracks.length) bg.footageEnabled = false;
  refreshFootageControls(); footageChanged();
}
/* Both of these strings are assembled around the track name, so the finished
 * pair is registered: "V1 · 轨道 1" is neither a dictionary entry nor a
 * pattern. The Chinese rendering is built even while English is active, so the
 * record exists before the first switch and a language change does not depend
 * on the controls being redrawn. */
function trackOptionLabel(name, index) {
  const english = `${name} · Track ${index + 1}`;
  const chinese = `${name} · ${t("Track", "zh-CN")} ${index + 1}`;
  rememberSource(chinese, english, "zh-CN");
  return currentLanguage === "zh-CN" ? chinese : english;
}
function removeTrackLabel(name) {
  const english = `Remove track ${name}`;
  const chinese = `${t("Remove track", "zh-CN")} ${name}`;
  rememberSource(chinese, english, "zh-CN");
  return currentLanguage === "zh-CN" ? chinese : english;
}
function refreshVisualTrackControls(clip) {
  const select = document.getElementById("clipTrack"); if (!select) return;
  const tracks = project.background.tracks ||= ["V1"];
  select.replaceChildren();
  tracks.forEach((name,i) => { const option = document.createElement("option"); option.value=i; option.textContent = trackOptionLabel(name, i); select.append(option); });
  const manager = document.getElementById("backgroundTrackManager"); manager.replaceChildren();
  tracks.forEach((name,i) => {
    const row = document.createElement("div"), label = document.createElement("span"), remove = document.createElement("button");
    label.textContent = `${name} · ${(project.background.clips || []).filter(c => (c.track||0)===i).length} clips`;
    remove.type="button"; remove.textContent="×"; remove.title=t("Remove track"); remove.setAttribute("aria-label", removeTrackLabel(name));
    remove.onclick=()=>removeBackgroundTrack(i); row.append(label,remove); manager.append(row);
  });
  if (clip) { select.value = clip.track || 0; document.getElementById("clipTransition").value = clip.transition || "cut"; }
  document.getElementById("fxTrigger").value = project.background.effects?.trigger || "beat";
}
function initVisualTracks() {
  document.getElementById("fxTrigger").onchange = async event => {
    (project.background.effects ||= {}).trigger = event.target.value;
    if (event.target.value === "transient" && project.audioAssetId) await ensureAnalysis();
    scheduleSave();
  };
  document.getElementById("addVisualTrack").onclick = () => {
    const tracks = project.background.tracks ||= ["V1"];
    if (tracks.length >= 4) return toast(t("Maximum four background tracks."));
    tracks.push(`V${tracks.length+1}`); refreshFootageControls(); footageChanged();
  };
  document.getElementById("addVisualClip").onclick = () => {
    const bg = project.background;
    const label = document.querySelector("#visualSelect option:checked")?.textContent || bg.visual;
    const settings = clone(bg);
    for (const key of ["clips","mediaLibrary","tracks","effects","effectOnsets","assetId","url","name","imageAsset","videoAsset"]) delete settings[key];
    const asset = {id:`visual-${crypto.randomUUID()}`,kind:"visual",name:`${label} · ${bg.sceneKit || ""}`,duration:5,size:0,settings};
    (bg.mediaLibrary ||= []).push(asset); refreshFootageControls(); scheduleSave();
  };
  document.getElementById("clipTrack").onchange = event => {
    const clip = selectedFootage(); if (!clip) return;
    clip.track = Number(event.target.value); refreshFootageControls(); footageChanged();
  };
  document.getElementById("clipTransition").onchange = event => {
    const clip = selectedFootage(); if (!clip) return;
    clip.transition = event.target.value;
    if (clip.transition !== "cut" && !(clip.fadeIn > 0)) clip.fadeIn = .35;
    refreshFootageControls(); footageChanged();
  };
}
