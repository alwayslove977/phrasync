"""Verify real Windows STA dispatch/owner binding without installing any update."""
import asyncio
import json
import threading
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import clr
clr.AddReference('System.Windows.Forms')
from System import Action
from System.Threading import Thread, ThreadStart, ApartmentState
from System.Windows.Forms import Application, ApplicationContext, Form
from winrt.windows.services.store import StoreContext
from winrt.runtime.interop import initialize_with_window
from phrasync import store_updates

ready = threading.Event()
state = {}
def ui():
    try:
        state['thread'] = threading.get_ident()
        state['form'] = Form()
        state['hwnd'] = state['form'].Handle.ToInt64()
        state['loop'] = ApplicationContext()
        ready.set()
        Application.Run(state['loop'])
        state['form'].Dispose()
    except Exception as exc:
        state['error'] = exc
        ready.set()

thread = Thread(ThreadStart(ui))
thread.SetApartmentState(ApartmentState.STA)
thread.Start()
assert ready.wait(15), 'STA loop did not start'
if 'error' in state:
    raise state['error']

class FakeStore:
    def request_download_and_install_store_package_updates_async(self, updates):
        assert threading.get_ident() == state['thread']
        assert updates == ['synthetic-update']
        return SimpleNamespace(progress=None)

original_context, original_owner = store_updates._context, store_updates._initialize_owner
try:
    store_updates.bind_window(SimpleNamespace(native=state['form']))
    store_updates._context = FakeStore
    def owner(context, hwnd):
        assert threading.get_ident() == state['thread']
        assert hwnd == state['hwnd']
        # Real Store object / real HWND, but NO query, download or installation.
        real_context = StoreContext.get_default()
        initialize_with_window(real_context, hwnd)
        state['ownerInitialized'] = True
    store_updates._initialize_owner = owner
    result = asyncio.run(asyncio.to_thread(store_updates._start_install_on_ui,['synthetic-update']))
    assert result[1].progress is store_updates._on_progress and state['ownerInitialized']
    print(json.dumps({'staDispatch':True,'realStoreOwnerInitialized':True,'storeInstallationRequested':False}),flush=True)
finally:
    store_updates._context, store_updates._initialize_owner = original_context, original_owner
    store_updates.bind_window(None)
    state['form'].Invoke(Action(state['loop'].ExitThread))
    thread.Join(5000)
