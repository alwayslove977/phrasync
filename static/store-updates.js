"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const translate = value => typeof window.t === "function" ? window.t(value) : value;
  let packaged = false, available = false, busy = false;
  const states = {
    retrying: "Microsoft Store could not download the update. Refreshing the request and trying once more…",
    completed: "Microsoft Store reports installation complete. Close Phrasync and reopen it from Start. The new version will be verified at launch.",
    unverified: "Installation could not be verified. Open Microsoft Store to review the update before restarting.",
    canceled: "Update canceled. No further installation was requested. You can try again when ready.",
    "low-battery": "Connect your computer to power, then try the update again.",
    "wifi-required": "Connect to Wi-Fi, then try the update again.",
    "wifi-recommended": "Microsoft Store recommends Wi-Fi for this update. Connect to Wi-Fi and try again.",
    pending: "The update is pending in Microsoft Store. Open Microsoft Store to review it.",
    downloading: "Microsoft Store is downloading the update. Open Microsoft Store to review its progress.",
    deploying: "Microsoft Store is installing the update. Phrasync may close.",
    "other-error": "Microsoft Store reported an installation error. See Diagnostics or open Microsoft Store to try again."
  };
  function message(value) {
    const parts = String(value).match(/^(.*?)( Error code: 0x[0-9A-F]{8}\.)$/);
    $("storeUpdateMessage").textContent = parts ? translate(parts[1]) + parts[2].replace("Error code:", translate("Error code:")) : translate(value);
  }
  function showInstall(value) { available = value; $("storeUpdateInstall").hidden = !value; }
  function setBusy(value) {
    busy = value;
    $("storeUpdateCheck").disabled = value || !packaged;
    $("storeUpdateInstall").disabled = value;
  }
  function progress(data) {
    const bar = $("storeUpdateProgress");
    bar.hidden = !data.busy;
    if (Number.isFinite(data.percent)) bar.value = data.percent;
    else bar.removeAttribute("value");
    if (data.busy) {
      const state = states[data.state] || "Waiting for Microsoft Store…";
      message(translate(state) + (Number.isFinite(data.percent) ? ` ${data.percent}%` : ""));
    }
  }
  async function request(path) {
    const response = await fetch(path, {method: /\/(status|progress)$/.test(path) ? "GET" : "POST", cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Microsoft Store could not be reached.");
    return data;
  }
  async function status() {
    if (busy) return;
    setBusy(true); showInstall(false); $("storeUpdateOpen").hidden = true;
    try {
      const data = await request("/api/store-updates/status");
      packaged = Boolean(data.packaged);
      $("storeUpdateVersion").textContent = `Phrasync ${data.version}`;
      message(packaged ? "Ready to check Microsoft Store for updates."
        : "This is a local preview. Update checks work after installing Phrasync from Microsoft Store.");
      if (data.previous_update === "not-applied") message("The previous update was not applied. Check again or open Microsoft Store. Your installed version is unchanged.");
      if (data.previous_update === "verified") message("The updated package is now running.");
    } catch (error) { packaged = false; message(error.message); }
    finally { setBusy(false); }
  }
  async function check() {
    if (!packaged || busy) return;
    setBusy(true); showInstall(false); $("storeUpdateOpen").hidden = true;
    message("Checking Microsoft Store…");
    try {
      const data = await request("/api/store-updates/check");
      showInstall(Boolean(data.available));
      message(data.available ? "A Phrasync update is available." : "Phrasync is up to date.");
    } catch (error) { message(error.message); $("storeUpdateOpen").hidden = false; }
    finally { setBusy(false); }
  }
  function confirmInstall() {
    const dialog = $("storeUpdateConfirm");
    dialog.returnValue = "";
    return new Promise(resolve => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "install"), {once: true});
      dialog.showModal();
    });
  }
  async function install() {
    if (!packaged || !available || busy) return;
    setBusy(true);
    try {
      if (!await confirmInstall()) return;
      $("storeUpdateOpen").hidden = true;
      message("Microsoft Store is downloading and installing the update. The app may close.");
      $("storeUpdateProgress").hidden = false;
      $("storeUpdateProgress").removeAttribute("value");
      let polling = true;
      let timer;
      const poll = async () => {
        try { const data = await request("/api/store-updates/progress"); if (polling) progress(data); }
        catch (_) { /* Store may be closing this process to deploy the package. */ }
        if (polling) timer = setTimeout(poll, 700);
      };
      timer = setTimeout(poll, 700);
      let data;
      try { data = await request("/api/store-updates/install"); }
      finally { polling = false; clearTimeout(timer); $("storeUpdateProgress").hidden = true; }
      if (data.state === "up-to-date") { showInstall(false); message("Phrasync is up to date."); }
      else {
        message(states[data.state] || "Microsoft Store returned an unexpected update status. See Diagnostics or open Microsoft Store.");
        if (data.error_codes?.length) {
          const code = data.error_codes[0];
          if (code === "0x80244007") message("Microsoft Store/Windows Update could not download the update. Try again later or open Microsoft Store. Your installed version is unchanged.");
          $("storeUpdateMessage").textContent += ` ${translate("Error code:")} ${code}.`;
        }
        if (data.state === "completed") showInstall(false);
        else $("storeUpdateOpen").hidden = false;
      }
    } catch (error) {
      message(error.message); $("storeUpdateOpen").hidden = false;
    } finally { setBusy(false); }
  }
  async function startup() {
    await status();
    if (!packaged || busy) return;
    try {
      const data = await request("/api/store-updates/check");
      showInstall(Boolean(data.available));
      if (!data.available) return;
      const notify = () => {
        const open = document.querySelector("dialog[open]");
        if (open) { open.addEventListener("close", notify, {once: true}); return; }
        $("storeUpdateAvailable").showModal();
      };
      notify();
    } catch (_) { /* Automatic checks never interrupt editing with an error. */ }
  }
  document.addEventListener("DOMContentLoaded", () => {
    $("settingsButton").addEventListener("click", status);
    $("storeUpdateCheck").addEventListener("click", check);
    $("storeUpdateInstall").addEventListener("click", install);
    $("storeUpdateAvailable").addEventListener("close", () => {
      if ($("storeUpdateAvailable").returnValue === "settings") $("settingsButton").click();
    });
    setTimeout(startup, 1500);
    $("storeUpdateOpen").addEventListener("click", async () => {
      if (!packaged || busy) return;
      try {
        if (!window.pywebview?.api?.open_store_updates) throw new Error("Open Microsoft Store from the Windows Start menu.");
        await window.pywebview.api.open_store_updates();
      } catch (error) { message(error.message); }
    });
  });
})();
