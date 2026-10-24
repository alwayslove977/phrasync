# Phrasync 0.5.0

GitHub source release. The matching Windows installer channel is [Microsoft Store](https://apps.microsoft.com/detail/9NF9JBG2PKHX). Package 0.5.0.0 was submitted for certification on October 24, 2026, with automatic publication after approval. The previous approved version remains available until rollout completes.

Thanks to Especiel-EA for the detailed report, logs and experimental patches in [issue #5](https://github.com/jaydemks/phrasync/issues/5).

## Export reliability

The local frame bridge handles idle browser preconnections concurrently and reuses HTTP connections. An idle socket can no longer block the actual frame upload. Frame consumption remains serial and authenticated, preserving ordering and bounded per-frame memory.

Older projects that reference an image or video by asset ID are rebuilt with verified local media metadata before export. Missing files are reported before opening the export browser.

Browser errors now preserve their original message and stack, with the failing timeline time, instead of disappearing behind a generic missing-frame error. Diagnostics distinguish deliberately selected FFmpeg composition from an unavailable browser codec.

Compositions with 3D typography can now encode the finished canvas directly through the browser's hardware-preferred H.264 encoder, including footage, effects and offline spectrum analysis. Compatible H.264 footage is decoded sequentially from its original compressed packets rather than repeatedly seeking to keyframes. Queues and decoded frames remain bounded. Custom bitrate still includes H.264 filler where necessary.

Flat PIL typography and unsupported browser configurations retain the complete lossless canvas path. Its FFmpeg encoder uses NVENC only after a successful device/resolution probe and can restart the entire pass on CPU if the device fails. Pixel-readback failure can use lossless PNG transfer. No text, effects or footage are removed to obtain the speed improvement.

Preview footage clocks now actively converge to the audio clock instead of accepting a persistent 200 ms lag. Trimmed upcoming clips pre-roll before their visible cut, including clips that reuse the same source file.

GPU-encoded exports declare their colour matrix explicitly so players do not introduce a colour shift by assuming the wrong matrix. This metadata adjustment does not add another video encode.

## Audio-reactive visuals

Offline spectrum analysis now uses the preview analyser's 48 kHz sample rate, 256-point Blackman FFT, frequency bins, dB limits and byte quantisation. The WebGL spectrum overlay, 3D wave and equalizer receive the appropriate bins. Smoothing runs at a fixed timeline rate, with bounded pre-roll for IN/OUT exports. Live browser scheduling and audio latency can still differ slightly from deterministic offline rendering.

## Timing and transcription

Decimal IN/OUT values no longer create a phantom extra frame. FFmpeg canvas exports preserve exact frame timestamps instead of rounding them through a millisecond-based intermediate container.

The post-render check accepts valid, decodable exports shorter than 0.1 seconds, including a single-frame selection. Missing, invalid or zero duration is still rejected.

Source installations avoid the faster-whisper 1.2.1/PyAV 19 incompatibility. Existing affected environments can decode audio through FFmpeg, including fixed-language transcription, without changing unrelated decoder errors or the transcription model.

## Verification

Automated tests cover browser exceptions, trusted media restoration, raw and PNG transfer, rejected input, duplicate-frame prevention, audio compatibility, spectrum history and exact frame timestamps. Real render matrices and the local Windows candidate are checked separately. Results are recorded locally under `qa_out/render-050`.

293 automated Windows tests passed. Structural matrices covered 70 source cases and 67 Windows-package cases, with targeted cases repeated after the final colour-metadata adjustment. In the real 1080p30 project, the same 16-second range with layered footage, effects and 3D text took 15.765 seconds to export on an RTX 3090, compared with the initial diagnostic run's 101.093 seconds. GPU encoding and decoding were observed. This measurement is specific to that composition and hardware; native macOS/Linux packages have not been verified.

Issue #5 did not include the original project and its media. Its exact failure still needs confirmation by the reporter with the new version. No claim is made that every driver or arbitrary project combination has been exhaustively tested.
