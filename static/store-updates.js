"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const translate = value => typeof window.t === "function" ? window.t(value) : value;
  let packaged = false, available = false, busy = false;
  const states = {
    completed: "Update installed. Restart Phrasync to use the new version.",
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
  async function request(path) {
    const response = await fetch(path, {method: path.endsWith("/status") ? "GET" : "POST", cache: "no-store"});
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
      const data = await request("/api/store-updates/install");
      if (data.state === "up-to-date") { showInstall(false); message("Phrasync is up to date."); }
      else {
        message(states[data.state] || "Microsoft Store returned an unexpected update status. See Diagnostics or open Microsoft Store.");
        if (data.state === "completed") showInstall(false);
        else $("storeUpdateOpen").hidden = false;
      }
    } catch (error) {
      message(error.message); $("storeUpdateOpen").hidden = false;
    } finally { setBusy(false); }
  }
  document.addEventListener("DOMContentLoaded", () => {
    $("settingsButton").addEventListener("click", status);
    $("storeUpdateCheck").addEventListener("click", check);
    $("storeUpdateInstall").addEventListener("click", install);
    $("storeUpdateOpen").addEventListener("click", async () => {
      if (!packaged || busy) return;
      try {
        if (!window.pywebview?.api?.open_store_updates) throw new Error("Open Microsoft Store from the Windows Start menu.");
        await window.pywebview.api.open_store_updates();
      } catch (error) { message(error.message); }
    });
  });
})();
