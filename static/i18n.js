"use strict";

const LANGUAGE_KEY = "phrasync.language";
const ONBOARDING_KEY = "phrasync.onboarding.v2";

const ITALIAN = {
  "Error code:": "Codice errore:",
  "The Microsoft Store update service is unavailable on this device.": "Il servizio di aggiornamento Microsoft Store non è disponibile su questo dispositivo.",
  "Could not check Microsoft Store for updates. Try again later or open the Store listing.": "Impossibile verificare gli aggiornamenti Microsoft Store. Riprova più tardi oppure apri la pagina dello Store.",
  "Microsoft Store could not be reached.": "Impossibile contattare Microsoft Store.",
  "Update Phrasync": "Aggiorna Phrasync",
  "Not now": "Non ora",
  "Open Microsoft Store": "Apri Microsoft Store",
  "Save your project before continuing. Microsoft Store may close Phrasync to install the update. Your saved projects and media stay on this computer.": "Salva il progetto prima di continuare. Microsoft Store potrebbe chiudere Phrasync per installare l'aggiornamento. I progetti salvati e i file multimediali rimangono su questo computer.",
  "Update canceled. No further installation was requested. You can try again when ready.": "Aggiornamento annullato. Non sono state richieste altre installazioni. Puoi riprovare quando vuoi.",
  "Connect your computer to power, then try the update again.": "Collega il computer all'alimentazione, poi riprova l'aggiornamento.",
  "Connect to Wi-Fi, then try the update again.": "Connettiti al Wi-Fi, poi riprova l'aggiornamento.",
  "Microsoft Store recommends Wi-Fi for this update. Connect to Wi-Fi and try again.": "Microsoft Store consiglia il Wi-Fi per questo aggiornamento. Connettiti al Wi-Fi e riprova.",
  "The update is pending in Microsoft Store. Open Microsoft Store to review it.": "L'aggiornamento è in attesa su Microsoft Store. Apri Microsoft Store per verificarlo.",
  "Microsoft Store is downloading the update. Open Microsoft Store to review its progress.": "Microsoft Store sta scaricando l'aggiornamento. Apri Microsoft Store per verificare l'avanzamento.",
  "Microsoft Store is installing the update. Phrasync may close.": "Microsoft Store sta installando l'aggiornamento. Phrasync potrebbe chiudersi.",
  "Microsoft Store reported an installation error. See Diagnostics or open Microsoft Store to try again.": "Microsoft Store ha segnalato un errore d'installazione. Consulta la Diagnostica o apri Microsoft Store per riprovare.",
  "Microsoft Store returned an unexpected update status. See Diagnostics or open Microsoft Store.": "Microsoft Store ha restituito uno stato inatteso. Consulta la Diagnostica o apri Microsoft Store.",
  "Open Microsoft Store from the Windows Start menu.": "Apri Microsoft Store dal menu Start di Windows.",
  "Microsoft Store could not install the update. See Diagnostics for details or open Microsoft Store and try again.": "Microsoft Store non ha potuto installare l'aggiornamento. Consulta la Diagnostica per i dettagli oppure apri Microsoft Store e riprova.",
  "The Phrasync desktop window is not ready. Reopen the app and try again.": "La finestra desktop di Phrasync non è pronta. Riapri l'app e riprova.",
  "An update installation is already in progress.": "È già in corso l'installazione di un aggiornamento.",
  "Video rate control": "Controllo bitrate video",
  "Automatic quality (CRF)": "Qualità automatica (CRF)",
  "Custom bitrate (Mbps)": "Bitrate personalizzato (Mbps)",
  "Video bitrate (Mbps)": "Bitrate video (Mbps)",
  "For example: 50 or 150 Mbps. Higher rates create larger files.": "Per esempio: 50 o 150 Mbps. Bitrate maggiori generano file più grandi.",
  "Choose where to save your exports before starting a render.": "Scegli dove salvare gli export prima di avviare il rendering.",
  "Show exported MP4": "Mostra MP4 esportato",
  "Export folder path": "Percorso cartella export",
  "Enter an existing absolute folder path": "Inserisci il percorso completo di una cartella esistente",
  "middle mouse = pan · drag = move · edges = duration · Shift = ripple · Alt = no snap": "rotella premuta = scorri · trascina = sposta · bordi = durata · Shift = sposta successivi · Alt = senza aggancio",
  "Scroll timeline": "Scorri la timeline",
  "App updates": "Aggiornamenti dell'app",
  "Checking installation…": "Verifica dell'installazione…",
  "Check for new Phrasync versions and install them through Microsoft Store. Your projects remain on this computer.": "Controlla le nuove versioni di Phrasync e installale tramite Microsoft Store. I progetti rimangono su questo computer.",
  "Open settings to check the installation.": "Apri le impostazioni per verificare l'installazione.",
  "Check for updates": "Controlla aggiornamenti",
  "Install update": "Installa aggiornamento",
  "This is a local preview. Update checks work after installing Phrasync from Microsoft Store.": "Questa è una versione di prova locale. Il controllo degli aggiornamenti funzionerà dopo l'installazione da Microsoft Store.",
  "Ready to check Microsoft Store for updates.": "Pronto a cercare aggiornamenti su Microsoft Store.",
  "Checking Microsoft Store…": "Controllo di Microsoft Store…",
  "A Phrasync update is available.": "È disponibile un aggiornamento di Phrasync.",
  "Phrasync is up to date.": "Phrasync è aggiornato.",
  "Install this Phrasync update now? Save your project first; the app may close during installation.": "Vuoi installare ora l'aggiornamento di Phrasync? Salva prima il progetto: l'app potrebbe chiudersi durante l'installazione.",
  "Microsoft Store is downloading and installing the update. The app may close.": "Microsoft Store sta scaricando e installando l'aggiornamento. L'app potrebbe chiudersi.",
  "Update installed. Restart Phrasync to use the new version.": "Aggiornamento installato. Riavvia Phrasync per usare la nuova versione.",
  "Diagnostics": "Diagnostica",
  "Open support diagnostics": "Apri la diagnostica di supporto",
  "LOCAL SUPPORT": "SUPPORTO LOCALE",
  "Close diagnostics": "Chiudi diagnostica",
  "Windows, CPU, GPU, RAM, app version and recent errors are included. Media files, project contents and saved tokens are not attached. Error messages may contain file paths: review the report before sharing.": "Il rapporto include Windows, CPU, GPU, RAM, versione dell'app ed errori recenti. Non allega file multimediali, contenuti dei progetti o token salvati. I messaggi di errore possono contenere percorsi: controlla il rapporto prima di condividerlo.",
  "Open to load the local report.": "Apri per caricare il rapporto locale.",
  "Loading local report…": "Caricamento del rapporto locale…",
  "Report ready — review before sharing.": "Rapporto pronto: controllalo prima di condividerlo.",
  "The local report could not be loaded.": "Impossibile caricare il rapporto locale.",
  "Report copied. Review before sharing.": "Rapporto copiato. Controllalo prima di condividerlo.",
  "Copy unavailable. Download the report instead.": "Copia non disponibile. Scarica il rapporto.",
  "Support report": "Rapporto di supporto",
  "Refresh": "Aggiorna",
  "Copy report": "Copia rapporto",
  "Download log": "Scarica log",
  "3D text tilt": "Inclinazione testo 3D",
  "3D text turn": "Rotazione laterale testo 3D",
  "3D text roll": "Rotazione sul piano testo 3D",
  "Reset text orientation": "Ripristina orientamento testo",
  "Rotate the entire phrase within the scene. Zero keeps it upright in world space.": "Ruota l’intera frase nella scena. A zero rimane verticale nello spazio 3D.",
  "Open water, moving light. Choose Daytime below; position the sun and moon independently.": "Mare aperto e luce in movimento. Scegli il momento del giorno qui sotto; posiziona sole e luna separatamente.",
  "Sun · horizontal": "Sole · posizione orizzontale",
  "Sun · elevation": "Sole · altezza",
  "Moon · horizontal": "Luna · posizione orizzontale",
  "Moon · elevation": "Luna · altezza",
  "Ocean waves": "Onde dell’oceano",
  "Studio": "Studio",
  "Picture · sound · words": "Immagini · suono · parole",
  "Check project": "Verifica progetto",
  "Odyssey · 3D worlds": "Odyssey · mondi 3D",
  "Odyssey · illustrated landscape": "Odyssey · paesaggio illustrato",
  "Art direction": "Direzione artistica",
  "Cinematic · natural light": "Cinema · luce naturale",
  "Storybook · painted worlds": "Illustrato · mondi dipinti",
  "Psychedelic · colour in motion": "Psichedelico · colore in movimento",
  "Secondary movement": "Movimento secondario",
  "None · steady camera": "Nessuno · camera stabile",
  "Sway · side to side": "Oscillazione · laterale",
  "Float · up and down": "Fluttuazione · verticale",
  "Orbit · gentle circles": "Orbita · cerchi leggeri",
  "Movement strength": "Intensità del movimento",
  "Direction shapes the world. Secondary movement adds motion along that route.": "La direzione struttura il mondo. Il movimento secondario si aggiunge lungo quel percorso.",
  "Travel left": "Viaggia a sinistra",
  "Travel right": "Viaggia a destra",
  "Travel up": "Viaggia verso l'alto",
  "Travel down": "Viaggia verso il basso",
  "MP4/WebM · up to 16 GB · long-form video": "MP4/WebM · fino a 16 GB · video lunghi",
  "Importing": "Importazione",
  "Checking media…": "Verifica del file…",
  "Import interrupted. Check that Phrasync is still running and try again.": "Importazione interrotta. Verifica che Phrasync sia aperto e riprova.",
  "Import cancelled.": "Importazione annullata.",
  "The local server returned an invalid import response.": "Il server locale ha restituito una risposta di importazione non valida.",
  "local lyric & subtitle studio": "studio locale per lyric video e sottotitoli",
  "Project": "Progetto",
  "Untitled lyric video": "Lyric video senza titolo",
  "Checking engine": "Controllo motore",
  "Local engine status": "Stato motore locale",
  "Settings": "Impostazioni",
  "Open settings": "Apri impostazioni",
  "Save and stop Phrasync": "Salva e chiudi Phrasync",
  "Stop Phrasync": "Chiudi Phrasync",
  "Toggle light/dark theme": "Cambia tema chiaro/scuro",
  "Toggle theme": "Cambia tema",
  "Critic check": "Controllo qualità",
  "Render MP4": "Esporta MP4",
  "Build": "Crea",
  "live parameters": "parametri in tempo reale",
  "Project mode": "Modalità progetto",
  "Lyric Video": "Lyric video",
  "Subtitles": "Sottotitoli",
  "Turn a song into a kinetic lyric video.": "Trasforma una canzone in un lyric video cinetico.",
  "Transcribe speech and burn readable subtitles directly into audio or video.": "Trascrivi il parlato e integra sottotitoli leggibili direttamente nel video.",
  "Assets": "Risorse",
  "Add song": "Aggiungi canzone",
  "Add video or audio": "Aggiungi video o audio",
  "Choose": "Scegli",
  "Background": "Sfondo",
  "Dynamic": "Dinamico",
  "Image": "Immagine",
  "Video": "Video",
  "Built-in visual": "Visuale integrata",
  "Aurora drift": "Aurora fluttuante",
  "Orbit particles": "Particelle orbitali",
  "Audio equalizer": "Equalizzatore audio",
  "Neon horizon grid": "Griglia neon all'orizzonte",
  "Environment": "Ambiente",
  "Direction": "Direzione",
  "Forward": "Avanti",
  "Ascend": "Salita",
  "Dive": "Discesa",
  "Drift": "Deriva",
  "Bank": "Virata",
  "Beat-synced elements": "Elementi sincronizzati al beat",
  "Pulse props and lights to the beat": "Fa pulsare oggetti e luci a ritmo",
  "Particle flow": "Flusso di particelle",
  "Frequency-reactive particle wave": "Onda di particelle reattiva alle frequenze",
  "Wave": "Onda",
  "Wave intensity": "Intensità onda",
  "Speed": "Velocità",
  "Density": "Densità",
  "Regenerate world": "Rigenera ambiente",
  "Manual": "Manuale",
  "Automatic journey": "Percorso automatico",
  "Weather": "Meteo",
  "Clear": "Sereno",
  "Rain": "Pioggia",
  "Snow": "Neve",
  "Fog": "Nebbia",
  "Storm": "Temporale",
  "Falling leaves": "Foglie cadenti",
  "Daytime": "Ora del giorno",
  "Dawn": "Alba",
  "Day": "Giorno",
  "Sunset": "Tramonto",
  "Night": "Notte",
  "Season": "Stagione",
  "Spring": "Primavera",
  "Summer": "Estate",
  "Autumn": "Autunno",
  "Winter": "Inverno",
  "Choose background": "Scegli sfondo",
  "OCR image": "OCR immagine",
  "Extract lyric text": "Estrai il testo",
  "Import lyrics": "Importa testo",
  "Local transcription": "Trascrizione locale",
  "Whisper model": "Modello Whisper",
  "Tiny: fastest": "Tiny: più veloce",
  "Base: balanced": "Base: bilanciato",
  "Small: cleaner": "Small: più preciso",
  "Medium: accurate": "Medium: accurato",
  "Large v3: best": "Large v3: migliore",
  "Language mode": "Modalità lingua",
  "Speech VAD": "VAD parlato",
  "Leave off for sung vocals": "Disattiva per le parti cantate",
  "Transcribe song locally": "Trascrivi la canzone in locale",
  "Transcribe media locally": "Trascrivi il file in locale",
  "Local song transcription": "Trascrizione locale della canzone",
  "Local speech transcription": "Trascrizione locale del parlato",
  "Preparing transcription…": "Preparazione trascrizione…",
  "Transcription progress": "Avanzamento trascrizione",
  "Stop transcription": "Interrompi trascrizione",
  "Sync & timing": "Sincronizzazione e tempi",
  "No audio analysis": "Nessuna analisi audio",
  "Analyze audio": "Analizza audio",
  "Auto-align": "Allinea automaticamente",
  "Global offset": "Offset globale",
  "Word lead": "Anticipo parola",
  "Snap window": "Finestra di aggancio",
  "Snap strength": "Forza aggancio",
  "Snap phrases to beat": "Aggancia le frasi al beat",
  "Align phrase starts to the BPM grid": "Allinea l'inizio delle frasi alla griglia BPM",
  "Typography": "Tipografia",
  "Text space": "Spazio testo",
  "Style preset": "Stile predefinito",
  "Font character": "Carattere",
  "Custom font": "Font personalizzato",
  "Upload TTF/OTF": "Carica TTF/OTF",
  "Type size": "Dimensione testo",
  "Top line scale": "Scala riga superiore",
  "Text width": "Larghezza testo",
  "Vertical position": "Posizione verticale",
  "Line gap": "Spazio tra righe",
  "Text": "Testo",
  "Accent": "Accento",
  "Stroke": "Contorno",
  "Motion intensity": "Intensità movimento",
  "Extreme": "Estremo",
  "Standard": "Standard",
  "Subtle": "Leggero",
  "Static": "Statico",
  "Uppercase": "Maiuscolo",
  "Beat reaction": "Reazione al beat",
  "Pulse to the detected beat": "Pulsa seguendo il beat rilevato",
  "Background look": "Aspetto sfondo",
  "Shade": "Ombreggiatura",
  "Visual intensity": "Intensità visuale",
  "Grain": "Grana",
  "Motion": "Movimento",
  "Blur": "Sfocatura",
  "Canvas & export": "Formato ed esportazione",
  "Resolution": "Risoluzione",
  "Frame rate": "Fotogrammi al secondo",
  "Quality": "Qualità",
  "Show title-safe guide": "Mostra area sicura del titolo",
  "Live preview": "Anteprima in tempo reale",
  "Replay current lyric animation": "Ripeti animazione corrente",
  "Fullscreen preview": "Anteprima a schermo intero",
  "Add a song or scrub the timeline to preview": "Aggiungi una canzone o scorri la timeline per l'anteprima",
  "Play": "Riproduci",
  "Mute": "Disattiva audio",
  "Autosaved locally": "Salvato automaticamente in locale",
  "Lyrics": "Testo",
  "Paste or OCR lyrics": "Incolla il testo o usa OCR",
  "Paste or import transcript": "Incolla o importa trascrizione",
  "One subtitle cue per line…": "Un sottotitolo per riga…",
  "Import subtitles": "Importa sottotitoli",
  "Add media or scrub the timeline to preview": "Aggiungi un file o scorri la timeline per l'anteprima",
  "Building your lyric video": "Creazione del lyric video",
  "Burning subtitles into your video": "Integrazione dei sottotitoli nel video",
  "Add cue": "Aggiungi frase",
  "Paste or OCR text": "Incolla testo o usa OCR",
  "One lyric cue per line…": "Una frase per riga…",
  "Append": "Aggiungi",
  "Auto-time & replace": "Temporizza e sostituisci",
  "Sort": "Ordina",
  "Subtitle format": "Formato sottotitoli",
  "Export": "Esporta",
  "Load project": "Carica progetto",
  "Save project": "Salva progetto",
  "Reset": "Ripristina",
  "Timeline": "Timeline",
  "no audio": "nessun audio",
  "Onset": "Attacchi",
  "Beat": "Beat",
  "Free": "Libero",
  "Follow": "Segui",
  "no word selected": "nessuna parola selezionata",
  "Tap sync (T)": "Sincronizza a tempo (T)",
  "Split": "Dividi",
  "Reset words": "Ricalcola parole",
  "Quality report": "Rapporto qualità",
  "Running checks…": "Controlli in corso…",
  "Checks performed": "Controlli eseguiti",
  "Close": "Chiudi",
  "LOCAL SETTINGS": "IMPOSTAZIONI LOCALI",
  "Integrations": "Integrazioni",
  "Not configured": "Non configurato",
  "Whisper models": "Modelli Whisper",
  "Access token": "Token di accesso",
  "Show": "Mostra",
  "Remove saved token": "Rimuovi token salvato",
  "Save token": "Salva token",
  "LOCAL RENDER": "ESPORTAZIONE LOCALE",
  "Building your lyric video": "Creazione del lyric video",
  "Preparing critic pass…": "Preparazione controllo qualità…",
  "MP4 is ready.": "L'MP4 è pronto.",
  "Download MP4": "Scarica MP4",
  "Save video to": "Salva il video in",
  "Loading export folder…": "Caricamento cartella di esportazione…",
  "Choose folder": "Scegli cartella",
  "Open renders folder": "Apri cartella dei video esportati",
  "Open Phrasync default folder": "Apri cartella predefinita di Phrasync",
  "Start export": "Avvia esportazione",
  "Choose a folder and start export.": "Scegli una cartella e avvia l'esportazione.",
  "Browser Downloads folder": "Cartella Download del browser",
  "Export folder unavailable": "Cartella di esportazione non disponibile",
  "MP4 saved to": "MP4 salvato in",
  "Cancel render": "Annulla esportazione",
  "WELCOME TO PHRA//SYNC": "BENVENUTO IN PHRA//SYNC",
  "Local lyric videos, without the wait being a mystery": "Lyric video locali, con tempi di attesa sempre chiari",
  "Your first transcription downloads an AI model": "La prima trascrizione scarica un modello AI",
  "Choose a Whisper model and select": "Scegli un modello Whisper e premi",
  "Transcribe": "Trascrivi",
  ". The first run downloads that model to this computer. Phrasync will show the download percentage, transferred size, and estimated time remaining.": ". Al primo utilizzo il modello viene scaricato su questo computer. Phrasync mostrerà percentuale, dimensione trasferita e tempo rimanente stimato.",
  "It happens once per model.": "Succede una sola volta per modello.",
  "Later transcriptions start directly from the local copy.": "Le trascrizioni successive partono direttamente dalla copia locale.",
  "Your media stays local.": "I tuoi file restano locali.",
  "Audio, lyrics, transcripts, projects, and exports are not uploaded to Phrasync.": "Audio, testi, trascrizioni, progetti ed esportazioni non vengono caricati su Phrasync.",
  "NVIDIA acceleration is automatic.": "L'accelerazione NVIDIA è automatica.",
  "With a compatible NVIDIA GPU and current driver, transcription uses CUDA; otherwise the interface clearly reports CPU mode.": "Con una GPU NVIDIA compatibile e driver aggiornati, la trascrizione usa CUDA; altrimenti l'interfaccia indica chiaramente la modalità CPU.",
  "Start creating": "Inizia a creare",
  "Switch to Italian": "Passa all'italiano",
  "Switch to English": "Passa all'inglese",
  "Switch interface language": "Cambia lingua dell'interfaccia",
  "Local engine ready": "Motore locale pronto",
  "FFmpeg missing": "FFmpeg mancante",
  "Backend offline": "Backend non disponibile",
  "Transcribing locally…": "Trascrizione locale…",
  "Creating transcription job": "Creazione attività di trascrizione",
  "Transcription complete": "Trascrizione completata",
  "Transcription stopped": "Trascrizione interrotta",
  "Transcription failed": "Trascrizione non riuscita"
};

let currentLanguage = "en";

function translateExact(value, language = currentLanguage) {
  if (language === "en") return value;
  return ITALIAN[value] || value;
}

function translateTextNode(node, language) {
  if (!node.parentElement || node.parentElement.closest("script,style,[data-no-i18n]")) return;
  if (node.__phrasyncEnglish === undefined) node.__phrasyncEnglish = node.nodeValue;
  const original = node.__phrasyncEnglish;
  const trimmed = original.trim();
  if (!trimmed) return;
  const translated = translateExact(trimmed, language);
  const prefix = original.match(/^\s*/)?.[0] || "";
  const suffix = original.match(/\s*$/)?.[0] || "";
  node.nodeValue = `${prefix}${translated}${suffix}`;
}

function translateElement(root = document, language = currentLanguage) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => translateTextNode(node, language));
  const elements = root.querySelectorAll ? [root, ...root.querySelectorAll("[title],[aria-label],[placeholder]")] : [];
  for (const element of elements) {
    if (!element?.getAttribute) continue;
    for (const attribute of ["title", "aria-label", "placeholder"]) {
      const value = element.getAttribute(attribute);
      if (!value) continue;
      const key = {
        title: "phrasyncEnglishTitle",
        "aria-label": "phrasyncEnglishAriaLabel",
        placeholder: "phrasyncEnglishPlaceholder",
      }[attribute];
      if (!element.dataset[key]) element.dataset[key] = value;
      element.setAttribute(attribute, translateExact(element.dataset[key], language));
    }
  }
}

function updateLanguageButtons() {
  const target = currentLanguage === "en" ? "IT" : "EN";
  const title = currentLanguage === "en" ? "Switch to Italian" : "Switch to English";
  for (const button of document.querySelectorAll(".language-toggle")) {
    button.textContent = target;
    button.title = translateExact(title, currentLanguage);
  }
}

function setInterfaceLanguage(language) {
  currentLanguage = language === "it" ? "it" : "en";
  localStorage.setItem(LANGUAGE_KEY, currentLanguage);
  document.documentElement.lang = currentLanguage;
  translateElement(document, currentLanguage);
  updateLanguageButtons();
  document.dispatchEvent(new CustomEvent("phrasync-language-change", { detail: currentLanguage }));
}

function toggleInterfaceLanguage() {
  setInterfaceLanguage(currentLanguage === "en" ? "it" : "en");
}

function formatByteCount(value) {
  const bytes = Number(value || 0);
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

function formatEta(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return currentLanguage === "it" ? "stima del tempo in corso" : "estimating time remaining";
  if (value < 60) return currentLanguage === "it" ? `circa ${Math.ceil(value)} s rimanenti` : `about ${Math.ceil(value)} sec remaining`;
  const minutes = Math.max(1, Math.round(value / 60));
  return currentLanguage === "it" ? `circa ${minutes} min rimanenti` : `about ${minutes} min remaining`;
}

function formatTranscriptionJob(job) {
  if (job?.phase === "model-download") {
    const percent = job.total_bytes ? Math.min(99, Math.round(job.downloaded_bytes / job.total_bytes * 100)) : 0;
    const lead = currentLanguage === "it" ? "Download modello Whisper" : "Downloading Whisper model";
    const amount = job.total_bytes ? `${formatByteCount(job.downloaded_bytes)} / ${formatByteCount(job.total_bytes)}` : formatByteCount(job.downloaded_bytes);
    return `${lead}: ${job.total_bytes ? `${percent}% · ` : ""}${amount} · ${formatEta(job.eta_seconds)}`;
  }
  if (job?.phase === "model-load") {
    const accelerator = job.device === "cuda" ? "NVIDIA GPU" : "CPU";
    return currentLanguage === "it" ? `Caricamento modello su ${accelerator}…` : `Loading model on ${accelerator}…`;
  }
  return translateExact(job?.message || "Transcribing…");
}

function initI18n() {
  currentLanguage = localStorage.getItem(LANGUAGE_KEY) === "it" ? "it" : "en";
  document.querySelector("#languageToggle")?.addEventListener("click", toggleInterfaceLanguage);
  document.querySelector("#onboardingLanguageToggle")?.addEventListener("click", toggleInterfaceLanguage);
  document.querySelector("#onboardingHide")?.addEventListener("change", event => {
    if (event.target.checked) localStorage.setItem(ONBOARDING_KEY,"hidden");
    else localStorage.removeItem(ONBOARDING_KEY);
  });
  document.querySelector("#onboardingContinue")?.addEventListener("click", () => {
    if (document.querySelector("#onboardingHide")?.checked) localStorage.setItem(ONBOARDING_KEY, "hidden");
    else localStorage.removeItem(ONBOARDING_KEY);
    document.querySelector("#onboardingDialog")?.close();
  });
  setInterfaceLanguage(currentLanguage);
  document.querySelector("#onboardingHide").checked = localStorage.getItem(ONBOARDING_KEY) === "hidden";
  if (localStorage.getItem(ONBOARDING_KEY) !== "hidden") document.querySelector("#onboardingDialog")?.showModal();
}

window.t = translateExact;
window.initI18n = initI18n;
window.setInterfaceLanguage = setInterfaceLanguage;
window.toggleInterfaceLanguage = toggleInterfaceLanguage;
window.formatTranscriptionJob = formatTranscriptionJob;
