"use strict";

/*
 * DOM half of the interface localisation: walk the document, keep the live
 * page in sync, and own the language controls.
 *
 * Depends on i18n.js, which must be loaded first: it owns currentLanguage and
 * every lookup (translateExact/translateMessage/sourceText). This file never
 * assigns currentLanguage — setCurrentLanguage() is the engine's single writer.
 */

const ONBOARDING_KEY = "phrasync.onboarding.v2";

/* -------------------------------------------------------- DOM translation */

const SKIP_SELECTOR = [
  "script",
  "style",
  "pre",
  "code",
  "kbd",
  "[data-no-i18n]",
  "[data-user-content]",
  "[contenteditable='true']",
  ".cue-text",
  ".lyric-text"
].join(",");

const AUTO_TRANSLATE_ATTRIBUTES = ["title", "aria-label", "placeholder", "alt"];
const ATTRIBUTE_DATASETS = {
  title: "phrasyncEnglishTitle",
  "aria-label": "phrasyncEnglishAriaLabel",
  placeholder: "phrasyncEnglishPlaceholder",
  alt: "phrasyncEnglishAlt"
};
/* The exact attribute value the last pass left on screen (or observed when the
 * source was first recorded). Window code rewrites the same attribute when the
 * mode changes — "One lyric cue per line…" becomes "One subtitle cue per
 * line…" — so comparing the live value with this one is what tells a fresh
 * source apart from the translation this file just wrote. */
const ATTRIBUTE_RENDERED_DATASETS = {
  title: "phrasyncRenderedTitle",
  "aria-label": "phrasyncRenderedAriaLabel",
  placeholder: "phrasyncRenderedPlaceholder",
  alt: "phrasyncRenderedAlt"
};

function skipped(node) {
  const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  if (!element) return true;
  return Boolean(element.closest(SKIP_SELECTOR));
}

/** Project content must never be rewritten, even when it collides with a key. */
function looksLikeContent(text) {
  if (/[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(text)) return true;
  return text.length > 240;
}

function translateTextNode(node, language) {
  if (!node || skipped(node)) return;
  if (node.__phrasyncEnglish === undefined) node.__phrasyncEnglish = sourceText(node.nodeValue, language);
  const original = node.__phrasyncEnglish;
  if (!original || !original.trim()) return;
  if (looksLikeContent(original)) return;
  const trimmed = original.trim();
  if (!/[A-Za-z]/.test(trimmed)) return;
  const translated = language === "en" ? trimmed : translateMessage(trimmed, language);
  const prefix = original.match(/^\s*/)?.[0] || "";
  const suffix = original.match(/\s*$/)?.[0] || "";
  const target = `${prefix}${translated}${suffix}`;
  if (node.nodeValue !== target) node.nodeValue = target;
}

/* Resolve the English source of one attribute. The live value is either that
 * source, this file's translation of it, or a string window code has written
 * since — a new English source or the output of t(). Only a value that differs
 * from the last one rendered is re-examined, so repeated MutationObserver
 * callbacks cannot overwrite the recorded source with an older translation. */
function attributeSource(element, attribute, value, language) {
  const sourceKey = ATTRIBUTE_DATASETS[attribute];
  const renderedKey = ATTRIBUTE_RENDERED_DATASETS[attribute];
  if (element.dataset[renderedKey] === value) return element.dataset[sourceKey] || "";
  const source = sourceText(value, language);
  const usable = Boolean(source.trim()) && !looksLikeContent(source) && /[A-Za-z]/.test(source);
  element.dataset[sourceKey] = usable ? source : "";
  element.dataset[renderedKey] = value;
  return usable ? source : "";
}

function translateAttributes(element, language) {
  if (!element?.getAttribute) return;
  if (element.closest?.("[data-no-i18n],[data-user-content],[contenteditable='true']")) return;
  for (const attribute of AUTO_TRANSLATE_ATTRIBUTES) {
    const value = element.getAttribute(attribute);
    if (!value || !value.trim()) continue;
    const source = attributeSource(element, attribute, value, language);
    if (!source) continue;
    /* Labels only: the dictionary, then a rendering the window code registered
     * for an assembled label. Backend messages never reach an attribute. */
    const translated = translateAttributeText(source, language);
    if (translated === value) continue;
    element.setAttribute(attribute, translated);
    element.dataset[ATTRIBUTE_RENDERED_DATASETS[attribute]] = translated;
  }
}

function translateTree(root, language) {
  if (!root) return;
  if (root.nodeType === Node.TEXT_NODE) {
    translateTextNode(root, language);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) translateTextNode(node, language);
  const elements = root.querySelectorAll
    ? [root, ...root.querySelectorAll("[title],[aria-label],[placeholder],[alt]")]
    : [];
  for (const element of elements) translateAttributes(element, language);
}

let observer = null;
let applying = false;

function startObserver() {
  if (observer) return;
  observer = new MutationObserver(records => {
    if (applying) return;
    /* English needs no rendering, but a text node the page rewrites in place
     * still has to record its new source: the next switch to Chinese draws
     * from these records, so keeping the one captured at boot would bring the
     * old string back. */
    const translating = currentLanguage !== "en";
    applying = true;
    try {
      for (const record of records) {
        if (record.type === "characterData") {
          const node = record.target;
          const source = node.__phrasyncEnglish;
          if (source === undefined) {
            node.__phrasyncEnglish = sourceText(node.nodeValue, currentLanguage);
          } else if (source.trim()) {
            /* Only this file's own translation matches the expected rendering
             * of the recorded source. Anything else was written by the page,
             * so it becomes the source — never the translated text itself. */
            const expected = source.replace(source.trim(), translateMessage(source.trim(), currentLanguage));
            if (node.nodeValue !== expected) node.__phrasyncEnglish = sourceText(node.nodeValue, currentLanguage);
          }
          if (translating) translateTextNode(node, currentLanguage);
          continue;
        }
        if (!translating) continue;
        if (record.type === "attributes") {
          translateAttributes(record.target, currentLanguage);
          continue;
        }
        for (const added of record.addedNodes) {
          if (added.nodeType === Node.TEXT_NODE) translateTextNode(added, currentLanguage);
          else if (added.nodeType === Node.ELEMENT_NODE) translateTree(added, currentLanguage);
        }
      }
    } finally {
      applying = false;
    }
  });
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: AUTO_TRANSLATE_ATTRIBUTES
  });
}

/* ------------------------------------------------------------ public state */

function updateLanguageControls() {
  const active = SUPPORTED_LANGUAGES.find(item => item.code === currentLanguage) || SUPPORTED_LANGUAGES[1];
  const select = document.querySelector("#languageSelect");
  if (select && select.value !== currentLanguage) select.value = currentLanguage;
  for (const button of document.querySelectorAll(".language-toggle")) {
    button.textContent = active.short;
    button.title = currentLanguage === "zh-CN"
      ? translateExact("Switch to English")
      : translateExact("Switch to Chinese");
    button.dataset.noI18n = "";
  }
}

function setInterfaceLanguage(language, { persist = true } = {}) {
  const next = setCurrentLanguage(language);
  if (persist) {
    localStorage.setItem(LANGUAGE_KEY, next);
    localStorage.setItem(LANGUAGE_VERSION_KEY, "2");
  }
  document.documentElement.lang = next;
  applying = true;
  try {
    translateTree(document, next);
  } finally {
    applying = false;
  }
  updateLanguageControls();
  document.dispatchEvent(new CustomEvent("phrasync-language-change", { detail: next }));
}

function toggleInterfaceLanguage() {
  setInterfaceLanguage(currentLanguage === "zh-CN" ? "en" : "zh-CN");
}

/* ------------------------------------------------------------------- boot */

function initI18n() {
  setCurrentLanguage(preferredLanguage());

  const select = document.querySelector("#languageSelect");
  if (select) {
    select.textContent = "";
    for (const item of SUPPORTED_LANGUAGES) {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = item.label;
      option.dataset.noI18n = "";
      select.append(option);
    }
    select.dataset.noI18n = "";
    select.addEventListener("change", () => setInterfaceLanguage(select.value));
  }

  document.querySelector("#languageToggle")?.addEventListener("click", toggleInterfaceLanguage);
  document.querySelector("#onboardingLanguageToggle")?.addEventListener("click", toggleInterfaceLanguage);
  document.querySelector("#onboardingHide")?.addEventListener("change", event => {
    if (event.target.checked) localStorage.setItem(ONBOARDING_KEY, "hidden");
    else localStorage.removeItem(ONBOARDING_KEY);
  });
  document.querySelector("#onboardingContinue")?.addEventListener("click", () => {
    if (document.querySelector("#onboardingHide")?.checked) localStorage.setItem(ONBOARDING_KEY, "hidden");
    else localStorage.removeItem(ONBOARDING_KEY);
    document.querySelector("#onboardingDialog")?.close();
  });

  setInterfaceLanguage(currentLanguage);
  startObserver();

  const hide = document.querySelector("#onboardingHide");
  if (hide) hide.checked = localStorage.getItem(ONBOARDING_KEY) === "hidden";
  if (localStorage.getItem(ONBOARDING_KEY) !== "hidden") document.querySelector("#onboardingDialog")?.showModal();
}

window.initI18n = initI18n;
window.setInterfaceLanguage = setInterfaceLanguage;
window.toggleInterfaceLanguage = toggleInterfaceLanguage;
