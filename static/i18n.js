"use strict";

/*
 * Interface localisation engine.
 *
 * English is the source language: every string in the templates and modules is
 * authored in English, and the dictionaries in i18n-zh.js map those exact
 * strings to another language. Nothing here touches project content — lyric
 * text, cue text, file names and font names are explicitly skipped.
 *
 * The DOM half lives in i18n-dom.js. This file owns the language state and
 * every lookup, so it stays usable in a context without a document.
 */

const LANGUAGE_KEY = "phrasync.language";
const LANGUAGE_VERSION_KEY = "phrasync.language.v2";

const SUPPORTED_LANGUAGES = [
  { code: "zh-CN", label: "简体中文", short: "中" },
  { code: "en", label: "English", short: "EN" }
];

const DICTIONARIES = window.PHRASYNC_I18N || {};

let currentLanguage = "en";

/* --------------------------------------------------------------- helpers */

function normalizeLanguage(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  if (/^zh(-|_)?/i.test(text)) return "zh-CN";
  if (/^en(-|_)?/i.test(text)) return "en";
  const exact = SUPPORTED_LANGUAGES.find(item => item.code.toLowerCase() === text.toLowerCase());
  return exact ? exact.code : null;
}

function preferredLanguage() {
  const stored = normalizeLanguage(localStorage.getItem(LANGUAGE_KEY));
  if (stored) return stored;
  const candidates = navigator.languages?.length ? navigator.languages : [navigator.language || ""];
  for (const candidate of candidates) {
    if (/^zh/i.test(candidate || "")) return "zh-CN";
  }
  return "en";
}

function dictionary(language = currentLanguage) {
  return DICTIONARIES[language] || null;
}

/* currentLanguage has exactly one writer: this function. i18n-dom.js changes
 * the interface language through it, so the state never has two owners. */
function setCurrentLanguage(language) {
  currentLanguage = normalizeLanguage(language) || "en";
  return currentLanguage;
}

/* Interface copy is authored in English, but with another language active the
 * window code calls t("…") and then writes the *translated* string into the DOM.
 * That would lose the English original, so every pair t()/tm() produces is
 * recorded here: switching back to English then restores the source instead of
 * leaving the translated text in place. */
const producedSources = new Map();
/* The same pairs, in the other direction. A sentence assembled from several
 * fragments ("Local Whisper ready · CPU mode. The first…") is neither a
 * dictionary key nor a pattern match, so re-rendering it in the same language
 * has to find the translation through this record; without it a correctly
 * recovered English source would be written back as English. */
const producedRenderings = new Map();
const producedKey = (language, text) => `${language}\u0000${text}`;

/* Register one rendering of one English source. Both directions are
 * first-wins: the pair is written when the text is first produced, and a later
 * pass that arrives at a different rendering for the same source — another code
 * path, a stale re-render — must not rewrite what the interface already shows.
 * Callers that assemble a sentence build the Chinese rendering even while
 * English is active and pass "zh-CN" explicitly, so the pair exists *before*
 * the first language switch instead of after it. */
function rememberSource(translated, source, language = currentLanguage) {
  const text = String(translated ?? "");
  const origin = String(source ?? "");
  if (!text || !origin || text === origin || language === "en") return;
  const sourceKey = producedKey(language, text);
  if (!producedSources.has(sourceKey)) producedSources.set(sourceKey, origin);
  const renderingKey = producedKey(language, origin);
  if (!producedRenderings.has(renderingKey)) producedRenderings.set(renderingKey, text);
}

function producedSource(text, language) {
  return producedSources.get(producedKey(language, text)) || null;
}

function producedRendering(source, language) {
  return producedRenderings.get(producedKey(language, source)) || null;
}

/* Text that did not come from t() — translated template markup, backend
 * messages — is recovered from the dictionary itself. */
const reverseTables = Object.create(null);

function reverseDictionary(language) {
  if (reverseTables[language]) return reverseTables[language];
  const reversed = new Map();
  for (const [source, translated] of Object.entries(dictionary(language) || {})) {
    if (typeof translated !== "string" || !translated || translated === source) continue;
    if (!reversed.has(translated)) reversed.set(translated, source);
  }
  reverseTables[language] = reversed;
  return reversed;
}

/* Sentences assembled around a number or a title cannot be reversed by a table
 * lookup, so the shapes this window and the backend actually emit are listed. */
const SOURCE_PATTERNS = [
  [/^“(.*)”\s([\d.]+)\s秒（估算）·\s(\d+)\/(\d+)$/, m => `“${m[1]}” ${m[2]}s (estimated) · ${m[3]}/${m[4]}`],
  [/^版本\s(.+)$/, m => `Version ${m[1]}`],
  [/^(\d+)\s条字幕$/, m => `${m[1]} cues`],
  [/^字幕\s(\d+)$/, m => `Cue ${m[1]}`],
  [/^字幕\s(\d+)\s·\s([\d.]+)–([\d.]+)$/, m => `Cue ${m[1]} · ${m[2]}–${m[3]}`],
  [/^第\s(\d+)\s\/\s(\d+)\s页$/, m => `Page ${m[1]} / ${m[2]}`],
  [/^约\s(\d+)\s秒剩余$/, m => `about ${m[1]} sec remaining`],
  [/^约\s(\d+)\s分钟剩余$/, m => `about ${m[1]} min remaining`],
  [/^正在估算剩余时间$/, () => "estimating time remaining"],
  [/^正在渲染第\s(\d+)\/(\d+)\s帧（单遍编码）$/, m => `Rendering frame ${m[1]}/${m[2]} (single-pass encoder)`],
  [/^正在渲染第\s(\d+)\/(\d+)\s帧$/, m => `Rendering frame ${m[1]}/${m[2]}`],
  [/^正在渲染 WebGL 第\s(\d+)\/(\d+)\s帧$/, m => `Rendering WebGL frame ${m[1]}/${m[2]}`],
  [/^正在编码\s(\d+)\s帧$/, m => `Encoding ${m[1]} frames`],
  [/^正在导入：(.*)$/, m => `Importing: ${m[1]}`],
  [/^MP4 已保存到\s(.*)$/, m => `MP4 saved to ${m[1]}`],
  [/^MP4 导出完成。?$/, () => "MP4 render complete."],
  [/^正在\s(.+)\s上加载模型…$/, m => `Loading model on ${m[1]}…`],
  [/^项目已保存：(.*)$/, m => `Project saved: ${m[1]}`],
  [/^无法保存项目：(.*)$/, m => `Could not save project: ${m[1]}`],
  [/^无法打开项目：(.*)$/, m => `Could not load project: ${m[1]}`],
  [/^项目无效：(.*)$/, m => `Invalid project: ${m[1]}`],
  [/^导出失败：(.*)$/, m => `Export failed: ${m[1]}`],
  [/^已导出\s(MP4|WEBM|SRT|LRC|ASS|VTT)：(.*)$/i, m => `Exported ${m[1].toUpperCase()}: ${m[2]}`]
];

function reversePattern(text) {
  for (const [pattern, build] of SOURCE_PATTERNS) {
    const match = pattern.exec(text);
    if (match) return build(match);
  }
  return null;
}

/** Best guess at the English source of a string that is on screen right now. */
function sourceText(value, language = currentLanguage) {
  const text = String(value ?? "");
  if (!text.trim() || language === "en") return text;
  const trimmed = text.trim();
  const source = producedSource(trimmed, language)
    || reverseDictionary(language).get(trimmed)
    || reversePattern(trimmed);
  return source ? text.replace(trimmed, source) : text;
}

/* Dynamic messages are assembled by the Python backend, so they can never be
 * dictionary keys. These patterns keep the numbers readable while translating
 * the sentence that wraps them. */
const MESSAGE_PATTERNS = [
  [/^Rendering frame (\d+)\/(\d+) \(single-pass encoder\)$/, m => `正在渲染第 ${m[1]}/${m[2]} 帧（单遍编码）`],
  [/^Rendering frame (\d+)\/(\d+)$/, m => `正在渲染第 ${m[1]}/${m[2]} 帧`],
  [/^Rendering WebGL frame (\d+)\/(\d+)$/, m => `正在渲染 WebGL 第 ${m[1]}/${m[2]} 帧`],
  [/^Encoding (\d+) frames$/, m => `正在编码 ${m[1]} 帧`],
  /* The forms the download note is assembled in come before the catch-all:
   * its "(.*)" would otherwise swallow the estimate and leave it in English. */
  [/^Downloading Whisper model: (\d+)% · (.*) · about (\d+) min remaining$/, m => `正在下载 Whisper 模型：${m[1]}% · ${m[2]} · 约 ${m[3]} 分钟剩余`],
  [/^Downloading Whisper model: (.*) · about (\d+) min remaining$/, m => `正在下载 Whisper 模型：${m[1]} · 约 ${m[2]} 分钟剩余`],
  [/^Downloading Whisper model: (.*) · about (\d+) sec remaining$/, m => `正在下载 Whisper 模型：${m[1]} · 约 ${m[2]} 秒剩余`],
  [/^Downloading Whisper model: (.*) · estimating time remaining$/, m => `正在下载 Whisper 模型：${m[1]} · 正在估算剩余时间`],
  [/^Downloading Whisper model: (.*)$/, m => `正在下载 Whisper 模型：${m[1]}`],
  [/^Downloading Whisper (.+?): (.*)$/, m => `正在下载 Whisper ${m[1]}：${m[2]}`],
  [/^Whisper (.+?) downloaded\. Loading model…$/, m => `Whisper ${m[1]} 已下载，正在加载模型…`],
  [/^Loading model on (CPU|NVIDIA GPU)…$/, m => `正在 ${m[1] === "CPU" ? "CPU" : "NVIDIA GPU"} 上加载模型…`],
  [/^Loading model on (.+)…$/, m => `正在 ${m[1]} 上加载模型…`],
  [/^Importing: (.+)$/, m => `正在导入：${m[1]}`],
  [/^MP4 saved to (.+)$/, m => `MP4 已保存到 ${m[1]}`],
  [/^MP4 render complete\.?$/, () => "MP4 导出完成。"],
  [/^Exported (MP4|WEBM|SRT|LRC|ASS|VTT): (.+)$/i, m => `已导出 ${m[1].toUpperCase()}：${m[2]}`],
  [/^Export failed: (.*)$/, m => `导出失败：${m[1]}`],
  [/^Project saved: (.*)$/, m => `项目已保存：${m[1]}`],
  [/^Could not save project: (.*)$/, m => `无法保存项目：${m[1]}`],
  [/^Could not load project: (.*)$/, m => `无法打开项目：${m[1]}`],
  [/^Invalid project: (.*)$/, m => `项目无效：${m[1]}`],
  [/^Could not stop Phrasync: (.*)$/, m => `无法退出 Phrasync：${m[1]}`],
  [/^Could not save token: (.*)$/, m => `无法保存令牌：${m[1]}`],
  [/^Could not remove token: (.*)$/, m => `无法删除令牌：${m[1]}`],
  [/^Could not load settings: (.*)$/, m => `无法读取设置：${m[1]}`],
  [/^Backend check failed: (.*)$/, m => `后端检查失败：${m[1]}`],
  [/^(\d+) cues?$/, m => `${m[1]} 条字幕`],
  [/^(.*?)\s·\s(\d+)\sclips?$/, m => `${m[1]} · ${m[2]} 个片段`],
  [/^“(.*)”\s([\d.]+)s \(estimated\) · (\d+)\/(\d+)$/, m => `“${m[1]}” ${m[2]} 秒（估算）· ${m[3]}/${m[4]}`],
  [/^Cue (\d+)$/, m => `字幕 ${m[1]}`],
  [/^Cue (\d+) · ([\d.]+)–([\d.]+)$/, m => `字幕 ${m[1]} · ${m[2]}–${m[3]}`],
  [/^Page (\d+) \/ (\d+)$/, m => `第 ${m[1]} / ${m[2]} 页`],
  [/^Version (.+)$/, m => `版本 ${m[1]}`],
  [/^about (\d+) min remaining$/, m => `约 ${m[1]} 分钟剩余`],
  [/^about (\d+) sec remaining$/, m => `约 ${m[1]} 秒剩余`],
  [/^estimating time remaining$/, () => "正在估算剩余时间"],
];

function translatePattern(value) {
  for (const [pattern, build] of MESSAGE_PATTERNS) {
    const match = pattern.exec(value);
    if (match) return build(match);
  }
  return null;
}

function translateExact(value, language = currentLanguage) {
  const text = String(value ?? "");
  if (!text) return text;
  if (language === "en") return text;
  const table = dictionary(language);
  if (table && Object.prototype.hasOwnProperty.call(table, text)) return table[text];
  const trimmed = text.trim();
  if (table && Object.prototype.hasOwnProperty.call(table, trimmed)) {
    return text.replace(trimmed, table[trimmed]);
  }
  return text;
}

/* Text the window code assembled around a number or a name ("V1 · Track 1",
 * the health note) is neither a key nor a pattern. It is only translatable
 * through the pair registered when it was produced; whitespace around the
 * string is preserved, exactly like the dictionary branch above. */
function translatedRendering(value, language) {
  const text = String(value ?? "");
  const trimmed = text.trim();
  if (!trimmed) return null;
  const assembled = producedRendering(trimmed, language);
  return assembled ? text.replace(trimmed, assembled) : null;
}

/** Translate a message that may be dynamic; falls back to the raw string.
 *  The order is fixed: exact dictionary entry, then a pattern rule, then a
 *  registered assembled rendering, then the raw string. A registered pair can
 *  therefore never shadow the dictionary or a pattern, and the same source
 *  yields the same text no matter which path registered it first. */
function translateMessage(value, language = currentLanguage) {
  const text = String(value ?? "");
  if (language === "en" || !text) return text;
  const direct = translateExact(text, language);
  if (direct !== text) return direct;
  const patterned = translatePattern(text);
  if (patterned) return patterned;
  return translatedRendering(text, language) ?? text;
}

/* Attribute values hold interface labels, never backend messages, so they stop
 * at the dictionary and the registered rendering instead of running through the
 * message patterns. */
function translateAttributeText(value, language = currentLanguage) {
  const text = String(value ?? "");
  if (language === "en" || !text) return text;
  const direct = translateExact(text, language);
  if (direct !== text) return direct;
  return translatedRendering(text, language) ?? text;
}

/* ------------------------------------------------------------ formatters */

function formatByteCount(value) {
  const bytes = Number(value || 0);
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

function etaText(seconds, language = currentLanguage) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return localize("estimating time remaining", language);
  if (value < 60) {
    return language === "zh-CN"
      ? `约 ${Math.ceil(value)} 秒剩余`
      : `about ${Math.ceil(value)} sec remaining`;
  }
  const minutes = Math.max(1, Math.round(value / 60));
  return language === "zh-CN" ? `约 ${minutes} 分钟剩余` : `about ${minutes} min remaining`;
}

function formatEta(seconds) {
  return etaText(seconds, currentLanguage);
}

function formatTranscriptionJob(job) {
  if (job?.phase === "model-download") {
    const percent = job.total_bytes ? Math.min(99, Math.round(job.downloaded_bytes / job.total_bytes * 100)) : 0;
    const amount = job.total_bytes
      ? `${formatByteCount(job.downloaded_bytes)} / ${formatByteCount(job.total_bytes)}`
      : formatByteCount(job.downloaded_bytes);
    const head = `${job.total_bytes ? `${percent}% · ` : ""}${amount}`;
    const chinese = `正在下载 Whisper 模型：${head} · ${etaText(job.eta_seconds, "zh-CN")}`;
    const english = `Downloading Whisper model: ${head} · ${etaText(job.eta_seconds, "en")}`;
    rememberSource(chinese, english, "zh-CN");
    return currentLanguage === "zh-CN" ? chinese : english;
  }
  if (job?.phase === "model-load") {
    const accelerator = job.device === "cuda" ? "NVIDIA GPU" : "CPU";
    const chinese = `正在 ${accelerator} 上加载模型…`;
    const english = `Loading model on ${accelerator}…`;
    rememberSource(chinese, english, "zh-CN");
    return currentLanguage === "zh-CN" ? chinese : english;
  }
  return localizeMessage(job?.message || "Transcribing…");
}

/* Window code localises its own strings through these two entry points; both
 * remember the English source so the text can be restored later. */
function localize(key, language = currentLanguage) {
  const text = String(key ?? "");
  if (!text) return text;
  const translated = translateExact(text, language);
  rememberSource(translated, text, language);
  return translated;
}

function localizeMessage(value, language = currentLanguage) {
  const text = String(value ?? "");
  if (!text) return text;
  const translated = translateMessage(text, language);
  rememberSource(translated, text, language);
  return translated;
}

window.t = localize;
window.tm = localizeMessage;
window.formatTranscriptionJob = formatTranscriptionJob;
window.PHRASYNC_LANGUAGES = SUPPORTED_LANGUAGES;
window.phrasyncLanguage = () => currentLanguage;
