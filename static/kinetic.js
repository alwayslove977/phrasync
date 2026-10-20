/*
 * Phrasync kinetic engine — shared timing + per-word animation model.
 *
 * This file is the single source of truth for how a lyric word looks at any
 * point in time. phrasync/kinetic.py mirrors the same math so the MP4 export
 * matches the browser preview frame for frame.
 */
(() => {
  "use strict";

  const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
  const mix = (a, b, t) => a + (b - a) * t;

  const ease = {
    linear: t => t,
    outCubic: t => 1 - Math.pow(1 - t, 3),
    outQuint: t => 1 - Math.pow(1 - t, 5),
    outExpo: t => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
    inOutCubic: t => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    outBack: t => {
      const c1 = 1.9, c3 = c1 + 1;
      return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
    },
    outElastic: t => {
      if (t <= 0) return 0;
      if (t >= 1) return 1;
      const p = 2 * Math.PI / 3;
      return Math.pow(2, -9 * t) * Math.sin((t * 10 - .75) * p) + 1;
    }
  };

  /* ------------------------------------------------------------------ *
   * Style presets
   * ------------------------------------------------------------------ */

  const PRESETS = {
    "kinetic-slam": {
      label: "Kinetic Slam",
      sizeScale: 1,
      layout: "inline",
      lead: 0.10,
      pendingAlpha: 0,
      hold: "cue",
      tail: 0.30,
      enter: "slam",
      active: "accent",
      past: "dim",
      caseTransform: "upper",
      lineHeight: 0.92,
      wordGap: 0.20,
      beatReact: 0.55,
      description: "Words slam in one by one with a controlled overshoot."
    },
    "neon-flux": {
      label: "Neon Flux",
      sizeScale: 1,
      layout: "inline",
      lead: 0.18,
      pendingAlpha: 0,
      hold: "cue",
      tail: 0.34,
      enter: "blur",
      active: "glow",
      past: "fade",
      caseTransform: "upper",
      lineHeight: 1.0,
      wordGap: 0.26,
      beatReact: 0.35,
      description: "Blur resolves on the beat with a neon glow on the active word."
    },
    "focus-word": {
      label: "Focus Word",
      sizeScale: 1.34,
      layout: "focus",
      lead: 0.05,
      pendingAlpha: 0,
      hold: "word",
      tail: 0.18,
      enter: "snap",
      active: "accent",
      past: "hidden",
      caseTransform: "upper",
      lineHeight: 0.9,
      wordGap: 0,
      beatReact: 0.8,
      description: "One giant word at a time with sharp short-form cuts."
    },
    "cascade": {
      layout: "cascade",
      label: "Cascade",
      sizeScale: 1,
      lead: 0.12,
      pendingAlpha: 0,
      hold: "cue",
      tail: 0.32,
      enter: "rise",
      active: "accent",
      past: "recede",
      caseTransform: "upper",
      lineHeight: 0.98,
      wordGap: 0.1,
      beatReact: 0.3,
      description: "Words stack from above while earlier words recede."
    },
    "wipe-fill": {
      label: "Wipe Fill",
      sizeScale: 1,
      layout: "inline",
      lead: 0,
      pendingAlpha: 0.42,
      hold: "cue",
      tail: 0.26,
      enter: "none",
      active: "wipe",
      past: "filled",
      caseTransform: "upper",
      lineHeight: 1.02,
      wordGap: 0.24,
      beatReact: 0.15,
      description: "The full phrase stays visible while colour fills each word in time."
    },
    "bold-stack": {
      label: "Bold Stack",
      sizeScale: 1,
      layout: "stack",
      lead: 0.09,
      pendingAlpha: 0,
      hold: "cue",
      tail: 0.30,
      enter: "pop",
      active: "accent",
      past: "none",
      caseTransform: "upper",
      lineHeight: 0.86,
      wordGap: 0.18,
      beatReact: 0.25,
      description: "A stacked poster title highlights the currently sung word."
    },
    "minimal": {
      label: "Minimal Caption",
      sizeScale: 0.5,
      layout: "inline",
      lead: 0.14,
      pendingAlpha: 0,
      hold: "cue",
      tail: 0.26,
      enter: "fade",
      active: "accent",
      past: "none",
      caseTransform: "none",
      lineHeight: 1.16,
      wordGap: 0.26,
      beatReact: 0,
      description: "Clean subtitle styling with restrained highlighting on a dark plate."
    }
  };

  PRESETS.spiral = { ...PRESETS["focus-word"], id:"spiral", label:"Spiral Flight", enter:"fade", lead:0, tail:.25, description:"Words orbit inward from depth and resolve at the sung syllable." };
  PRESETS.constellation = { ...PRESETS["neon-flux"], id:"constellation", label:"Word Constellation", layout:"focus", pendingAlpha:.18, lead:0, description:"Scattered words surround the current word, held at the centre." };
  const PRESET_ORDER = [
    "kinetic-slam", "neon-flux", "focus-word", "cascade", "wipe-fill", "bold-stack", "minimal", "spiral", "constellation"
  ];

  const LEGACY_PRESETS = { "center-punch": "kinetic-slam", "karaoke": "wipe-fill", "neon": "neon-flux" };

  /**
   * Preset with the project's own timing overrides applied.
   *
   * `style.wordLead` is how far ahead of the sung syllable a word may start its
   * entry animation, in seconds. Zero means it appears exactly on the beat.
   */
  function resolvedPreset(style) {
    const base = preset(style && style.preset);
    const lead = Number(style && style.wordLead);
    if (!Number.isFinite(lead)) return base;
    return { ...base, lead: Math.max(0, Math.min(0.5, lead)) };
  }

  function preset(id) {
    return PRESETS[id] || PRESETS[LEGACY_PRESETS[id]] || PRESETS["kinetic-slam"];
  }

  /* ------------------------------------------------------------------ *
   * Word timing
   * ------------------------------------------------------------------ */

  // Rough syllable count: vowel groups, with a floor of one per token.
  function syllableWeight(token) {
    const letters = String(token).toLowerCase().replace(/[^a-zà-öø-ÿ']/g, "");
    if (!letters) return 1;
    const groups = letters.match(/[aeiouyà-åè-ïò-öù-ü]+/g);
    let count = groups ? groups.length : 1;
    if (letters.length > 3 && /e$/.test(letters) && count > 1) count -= 1;
    return Math.max(1, count) + letters.length * 0.06;
  }

  /**
   * Return the word list for a cue, always timed and monotonic.
   * When Whisper timings are missing, syllable weight distributes the cue
   * duration far more musically than equal slots do.
   */
  function cueWords(cue) {
    let tokens = String(cue.text || "").replace(/\n/g, " ").split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];
    const stored = Array.isArray(cue.words) ? cue.words.filter(w => w && String(w.text || "").trim()) : [];
    if (stored.length && stored.map(w => w.text).join("").replace(/\s+/g, "") === String(cue.text || "").replace(/\s+/g, "")) {
      tokens = stored.map(w => String(w.text).trim());
    }
    const start = Number(cue.start) || 0;
    const end = Math.max(start + 0.2, Number(cue.end) || start + 1);

    if (stored.length === tokens.length) {
      let previous = -Infinity;
      return stored.map((word, index) => {
        const ws = Math.max(previous, Number(word.start ?? start));
        const we = Math.max(ws + 0.06, Number(word.end ?? ws + 0.25));
        previous = ws;
        return { text: tokens[index], start: ws, end: we, index, lineBreak: false };
      });
    }

    const weights = tokens.map(syllableWeight);
    const total = weights.reduce((sum, value) => sum + value, 0) || 1;
    const span = end - start;
    let cursor = start;
    return tokens.map((token, index) => {
      const length = span * (weights[index] / total);
      const word = { text: token, start: cursor, end: cursor + Math.max(0.08, length), index, lineBreak: false };
      cursor += length;
      return word;
    });
  }

  /* ------------------------------------------------------------------ *
   * Per-word state
   * ------------------------------------------------------------------ */

  const HIDDEN = Object.freeze({
    visible: false, opacity: 0, scale: 1, dx: 0, dy: 0, rotate: 0,
    blur: 0, fill: 0, fillAlpha: 0, glow: 0, role: "idle", weightBoost: 0, tracking: 0
  });

  /**
   * Compute the visual state of one word.
   *
   * @param {object} word   {text,start,end,index}
   * @param {object} cue    {start,end}
   * @param {number} t      playback seconds (already offset-corrected)
   * @param {object} spec   preset spec
   * @param {number} beat   0..1 pulse from the beat grid
   */
  function wordState(word, cue, t, spec, beat = 0) {
    const start = word.start;
    const end = Math.max(start + 0.06, word.end);
    const pending = spec.pendingAlpha || 0;
    // Allocate a phrase ahead of time, but never show its first glyph before
    // the first timed word. Pending-tint presets used to bypass even a zero
    // lead, while other presets exposed the phrase during their entry motion.
    const firstTimed = (cue.words || []).find(item => String(item.text || "").trim());
    const phraseOnset = Math.max(Number(cue.start) || 0,
      Number(firstTimed?.start ?? cue.start) || 0);
    if (t < phraseOnset || (spec.hold === "word" && t < start)) return HIDDEN;
    // Presets with a pending tint lay the whole line out from the cue start, so
    // the phrase stays optically centred while words light up one at a time.
    const appear = pending > 0 ? Math.min(cue.start - 0.05, start - spec.lead) : start - spec.lead;
    const entryFrom = start - spec.lead;
    const holdUntil = spec.hold === "word" ? end : cue.end;
    const vanish = holdUntil + spec.tail;

    if (t < appear || t > vanish) return HIDDEN;

    const state = {
      visible: true, opacity: 1, scale: 1, dx: 0, dy: 0, rotate: 0,
      blur: 0, fill: 0, fillAlpha: 1, glow: 0, role: "idle", weightBoost: 0, tracking: 0
    };

    // --- entry -------------------------------------------------------
    const entry = spec.lead > 0 ? clamp((t - entryFrom) / spec.lead) : 1;
    if (t < entryFrom) {
      state.opacity = pending;
    } else if (entry < 1) {
      switch (spec.enter) {
        case "slam": {
          const e = ease.outBack(entry);
          state.scale = mix(1.22, 1, e);
          state.opacity = ease.outCubic(clamp(entry * 1.9));
          state.blur = mix(6, 0, ease.outQuint(entry));
          state.dy = mix(-0.05, 0, e);
          break;
        }
        case "blur": {
          const e = ease.outQuint(entry);
          state.blur = mix(11, 0, e);
          state.opacity = ease.outCubic(entry);
          state.scale = mix(1.08, 1, e);
          break;
        }
        case "snap": {
          const e = ease.outExpo(clamp(entry * 1.3));
          state.scale = mix(0.72, 1, e);
          state.opacity = clamp(entry * 3);
          state.rotate = mix(-3, 0, e);
          break;
        }
        case "rise": {
          const e = ease.outQuint(entry);
          state.dy = mix(0.5, 0, e);
          state.opacity = ease.outCubic(entry);
          state.blur = mix(5, 0, e);
          break;
        }
        case "pop": {
          const e = ease.outBack(entry);
          state.scale = mix(0.8, 1, e);
          state.opacity = ease.outCubic(clamp(entry * 1.6));
          break;
        }
        case "fade":
          state.opacity = ease.outCubic(entry);
          state.dy = mix(0.12, 0, ease.outCubic(entry));
          break;
        default:
          state.opacity = 1;
      }
      if (pending > 0) state.opacity = Math.max(state.opacity, pending);
    }

    // --- role --------------------------------------------------------
    if (t < start) state.role = "pending";
    else if (t <= end) state.role = "active";
    else state.role = "past";

    if (state.role === "pending") {
      state.fill = 0;
    } else if (state.role === "active") {
      const p = clamp((t - start) / Math.max(0.001, end - start));
      // The accent ramps over ~90 ms rather than snapping on, which reads as
      // singable rather than as a cut.
      const ramp = ease.outCubic(clamp((t - start) / 0.09));
      state.fill = spec.active === "wipe" ? p : ramp;
      // A short attack spike right on the syllable, then settle.
      const attack = 1 - ease.outQuint(clamp((t - start) / 0.16));
      switch (spec.active) {
        case "accent":
          state.scale *= 1 + 0.09 * attack;
          state.weightBoost = 1;
          state.glow = 0.5 + 0.5 * attack;
          break;
        case "glow":
          state.glow = 1;
          state.scale *= 1 + 0.05 * attack;
          state.weightBoost = 1;
          break;
        case "wipe":
          state.glow = 0.35 * attack;
          state.weightBoost = p > 0.02 ? 1 : 0;
          break;
        default:
          break;
      }
    } else {
      // Sung words hand the accent back to the base colour, which is what makes
      // the current word read as "current" instead of everything going monochrome.
      const age = ease.inOutCubic(clamp((t - end) / 0.7));
      // The accent dissolves uniformly instead of un-wiping from the right.
      state.fill = 1;
      state.fillAlpha = spec.past === "filled" ? 1 : 1 - ease.inOutCubic(clamp((t - end) / 0.42));
      switch (spec.past) {
        case "dim":
          state.opacity *= mix(1, 0.42, age);
          state.scale *= mix(1, 0.965, age);
          break;
        case "fade":
          state.opacity *= mix(1, 0.3, age);
          state.blur += mix(0, 1.6, age);
          break;
        case "recede":
          state.opacity *= mix(1, 0.32, age);
          state.scale *= mix(1, 0.86, age);
          state.dy -= mix(0, 0.22, ease.outCubic(age));
          break;
        case "hidden":
          // Hard cut: the outgoing word must clear before the next one lands,
          // otherwise the two overlap on the same centre point.
          state.opacity *= 1 - ease.outExpo(clamp((t - end) / Math.max(0.05, spec.tail)));
          state.scale *= mix(1, 1.18, age);
          state.blur += mix(0, 8, age);
          break;
        case "filled":
        case "none":
        default:
          break;
      }
    }

    // --- exit at the end of the hold window --------------------------
    // --- phrase-level transition -------------------------------------
    // The outgoing phrase lifts away while the incoming one rises into place.
    // Without that vertical separation the two overlap on the same centre and
    // the dissolve reads as illegible double exposure.
    if (spec.tail > 0 && t > holdUntil) {
      const out = clamp((t - holdUntil) / spec.tail);
      if (spec.past !== "hidden") {
        state.opacity *= 1 - ease.outQuint(out);
        state.dy -= 0.38 * ease.outCubic(out);
        state.scale *= 1 - 0.07 * ease.outCubic(out);
        state.blur += 3 * out;
      }
    } else if (spec.tail > 0) {
      const rise = 1 - ease.outCubic(clamp((t - cue.start) / 0.30));
      state.dy += 0.30 * rise;
      state.opacity *= 1 - 0.55 * rise * rise;
    }

    // --- beat reaction ----------------------------------------------
    if (spec.beatReact > 0 && beat > 0 && state.role === "active") {
      const pulse = beat * spec.beatReact;
      state.scale *= 1 + 0.035 * pulse;
      state.glow = Math.min(1, state.glow + 0.25 * pulse);
    }

    if (spec.label === "Spiral Flight") {
      const progress = clamp((t-start)/Math.min(.45,Math.max(.08,end-start)*.7));
      const radius = (1-ease.outCubic(progress))*2.8, angle=(1-progress)*Math.PI*3;
      state.dx += Math.cos(angle)*radius; state.dy += Math.sin(angle)*radius;
      state.scale *= .25+.75*ease.outCubic(progress); state.rotate += (1-progress)*-35;
    } else if (spec.label === "Word Constellation" && state.role !== "active") {
      const phase=(word.index+1)*2.399963 + cue.start*.17;
      state.dx += Math.cos(phase)*(2.2+(word.index%3)*.8);
      state.dy += Math.sin(phase)*(1.2+(word.index%2)*.7);
      state.scale *= .32+(word.index%3)*.07; state.opacity *= .5;
      state.rotate = Math.sin(phase)*12;
    }
    state.opacity = clamp(state.opacity);
    return state;
  }

  /**
   * Cues that have anything to draw at time t.
   *
   * A phrase keeps painting through its tail while the next one is already
   * fading in, which is what turns the phrase change into a dissolve instead of
   * a cut. More than two can qualify when someone adds a cue over a
   * transcription; keep that manual cue visible instead of dropping it.
   */
  function activeCues(cues, t, spec) {
    const lead = Math.max(spec.lead, 0.05);
    const result = [];
    for (const cue of cues) {
      if (cue.start - lead > t) break;
      if (t <= cue.end + spec.tail) result.push(cue);
    }
    // A manual insertion is a correction to the transcribed line at that
    // point, not another layer that should be painted underneath it.
    const playing = cue => cue.start <= t && t < cue.end;
    const manual = result.filter(cue => cue.manual === true && playing(cue));
    if (manual.length) return manual.slice(-1);
    // Older projects did not tag manual cues; unlike transcribed phrases,
    // they usually have no stored word timings.
    const playingCues = result.filter(playing);
    if (playingCues.length > 1) {
      const untimed = playingCues.filter(cue => !cue.words || cue.words.length === 0);
      if (untimed.length) return untimed.slice(-1);
    }
    return result.slice(-2);
  }

  /**
   * Per-word size multiplier for the one-word-at-a-time layout, so a short word
   * fills the frame and a long one still fits. Deterministic from the token
   * length alone, which keeps the browser and the exporter in agreement.
   */
  function focusScale(text) {
    return clamp(7 / Math.max(2, String(text).length), 0.62, 1.5);
  }

  /**
   * 0..1 pulse that decays after each beat, used for background/word reaction.
   */
  function beatPulse(t, bpm, offset, decay = 0.22) {
    if (!bpm || bpm <= 0) return 0;
    const period = 60 / bpm;
    const phase = ((t - offset) % period + period) % period;
    return Math.exp(-phase / decay);
  }

  /**
   * Average glyph width as a fraction of the font size, per font family.
   * Used to decide line breaks identically in the browser and the exporter.
   */
  const FONT_WIDTH = {
    impact: 0.44, condensed: 0.46, modern: 0.53, serif: 0.51, mono: 0.60,
    bebas: 0.37, geometric: 0.59, rounded: 0.56, poster: 0.53, techno: 0.39, script: 0.59, jgothic: 0.6
  };

  /**
   * How many characters fit on one line for this canvas and type size.
   */
  function charBudget(style, canvas, spec) {
    const height = Number(canvas?.height) || 1080;
    const width = Number(canvas?.width) || 1920;
    const scale = spec && spec.sizeScale ? spec.sizeScale : 1;
    // Short edge, so a portrait canvas does not inflate the type.
    const reference = Math.min(height, width);
    const fontPx = (Number(style.fontSize) || 160) * (reference / 1080) * scale;
    const usable = width * (Number(style.maxWidth) || 88) / 100;
    const glyph = (FONT_WIDTH[style.fontPreset] || 0.46) * fontPx;
    return Math.max(6, Math.round(usable / Math.max(1, glyph)));
  }

  /**
   * Greedy wrap, then re-wrap with an evened-out budget so a phrase never ends
   * on a one-word orphan line.
   */
  function balancedWrap(words, budget) {
    const wrap = limit => {
      const lines = [[]];
      let width = 0;
      for (const word of words) {
        const cost = word.text.length + 1;
        if (lines[lines.length - 1].length && width + cost > limit) {
          lines.push([]);
          width = 0;
        }
        lines[lines.length - 1].push(word);
        width += cost;
      }
      return lines;
    };
    const chars = line => line.reduce((sum, word) => sum + word.text.length + 1, 0) - 1;
    const first = wrap(budget);
    if (first.length < 2) return first;

    const total = words.reduce((sum, word) => sum + word.text.length + 1, 0) - 1;
    const evened = Math.max(
      Math.max(...words.map(word => word.text.length)),
      Math.ceil(total / first.length)
    );
    const candidate = wrap(Math.min(budget, evened));
    const lines = candidate.length === first.length ? candidate : first;

    // Pull words down onto a stub final line ("...tears / the") until the last
    // two lines are roughly even.
    const last = lines[lines.length - 1];
    const previous = lines[lines.length - 2];
    while (previous.length > 1) {
      const move = previous[previous.length - 1];
      if (chars(last) >= chars(previous) - move.text.length - 1) break;
      if (chars(last) + move.text.length + 1 > budget) break;
      last.unshift(previous.pop());
    }
    return lines;
  }

  /**
   * Split cue words into display lines for the given layout.
   * `measure(text)` returns a relative width; charsPerLine is the budget.
   */
  function layoutLines(words, spec, charsPerLine = 22) {
    if (!words.length) return [];
    if (spec.layout === "focus") return words.map(word => [word]);
    if (spec.layout === "cascade") {
      // Short breath-sized chunks stacked vertically.
      return balancedWrap(words, Math.max(8, Math.round(charsPerLine * 0.55)));
    }

    const lines = balancedWrap(words, charsPerLine);
    if (spec.layout === "stack" && lines.length === 1 && lines[0].length > 2) {
      // Poster split: a smaller lead line over a heavier payoff line.
      const all = lines[0];
      const cut = Math.max(1, Math.min(all.length - 1, Math.ceil(all.length * 0.45)));
      return [all.slice(0, cut), all.slice(cut)];
    }
    return lines;
  }

  window.VFKinetic = {
    ease, clamp, mix, PRESETS, PRESET_ORDER, LEGACY_PRESETS,
    preset, resolvedPreset, cueWords, wordState, beatPulse, layoutLines, syllableWeight, focusScale, charBudget, activeCues
  };
})();
