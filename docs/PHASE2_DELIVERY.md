# Phrasync Phase 2 — macOS 打包交付报告（历史构建记录）

> **这是一份历史构建记录，不是当前源码的验收报告。**
>
> 本文描述的是 2026-10-19 那一天构建出的 `Phrasync.app`（0.4.7、x86_64）以及当时在
> 打包机上执行的验证。文中所有测试数量（23/23、8/8）、脚本数量、体积（963.7 MB /
> 922 MiB）、文件条目数与 `Sealed Resources files=1813` 都**只属于那个产物**，
> 不代表用当前 `macos-fixes` 源码重新构建的结果，也不随源码演进而更新。
>
> 当前源码可复跑的检查与打包规则，以 `packaging/macos/README.md`、
> `docs/MACOS_FIXES.md` 的 “Verification” 一节和 `tests/test_build_scripts.py`
> 为准。本轮文档校正**没有重新构建**，也没有重跑本文中的任何验收项。

版本 0.4.7 · 构建产物 `~/phrasync/dist/Phrasync.app` · 已安装至 `~/Desktop/Phrasync.app`
· 记录于 2026-10-19 16:20（历史时间，非本次修订时间）

本报告只记录**当时实际执行过**的验证。未执行的测试在「未验证 / 已知限制」一节单独列出，
不以编译成功代替运行成功。

---

## 1. 交付物

| 项目 | 路径 | 体积 |
| --- | --- | --- |
| 应用包（验收对象） | `~/phrasync/dist/Phrasync.app` | 922 MiB（du）/ 963.7 MB（字节） |
| 已安装副本（最终交付位置） | `~/Desktop/Phrasync.app` | 同上（`cp -Rc` APFS 克隆，签名校验通过） |
| 构建配置 | `packaging/macos/Phrasync.spec`、`build_app.sh`、`build_app.py`、`launcher.py`、`make_icns.py` | — |
| 中文化资源 | `static/i18n.js`、`static/i18n-dom.js`、`static/i18n-zh.js`、`static/index.html` | — |
| 打包说明（已更新） | `packaging/macos/README.md` | — |
| 内置浏览器说明（已更新） | `assets/browser/README.md` | — |

桌面旧版（Phase 1，179 MiB）已由用户删除，本报告不再保留旧包。

最终构建命令（实际执行，50 秒完成，复用 Analysis 缓存）：

```bash
cd ~/phrasync
env -u PYTHONPATH PHRASYNC_BUILD_AI=1 \
  .venv-build/bin/python -m PyInstaller --noconfirm \
  --distpath ~/phrasync/dist --workpath ~/phrasync/build/macos/pyinstaller-p13 \
  packaging/macos/Phrasync.spec
```

必须在**前台**并带沙箱豁免运行：后台执行会丢失豁免，PyInstaller 在 EXE 组装阶段的
`codesign --remove` 会报 `Operation not permitted`。等价入口是
`packaging/macos/build_app.sh --fast`（会先做架构与浏览器运行时预检）。

PyInstaller 6.22.3 · x86_64 thin · ad-hoc · `Sealed Resources files=1813`。

---

## 2. 架构、系统版本、签名

| 属性 | 实测值 | 证据 |
| --- | --- | --- |
| 主程序架构 | `Mach-O 64-bit executable x86_64` | `file` / `lipo -archs` |
| 原生库架构 | 全部 x86_64：`libpython3.12.dylib`、`libonnxruntime.1.23.2.dylib`、`ctranslate2/_ext…so`、`cv2.abi3.so`、`ffmpeg-macos-x86_64-v7.1`、`chrome-headless-shell` | 逐个 `lipo -archs` |
| 最低系统版本 | macOS 11.0（当时的 `Info.plist` 声明值，**并非真实下限**；后续已按 load command 实测改为 12.0，AI 包开关不改变该值。12.0 是由包内非 OCR 原生依赖推导的兼容目标，**未在 macOS 12 实机启动验证**。OCR 依赖要求 13.4，12.0–13.3 上 OCR 不保证可用；已发布的 `v0.4.7-macos.1` 压缩包**未重建**，仍声明 11.0，且该版本已下架；当前发布版为 `v0.4.7-macos.2`，声明 12.0） | `Info.plist` `LSMinimumSystemVersion`；修正见 `docs/MACOS_FIXES.md` |
| 版本号 | 0.4.7 | `CFBundleShortVersionString` |
| Bundle ID | `com.phrasync.desktop` | `codesign -dv` |
| 签名 | ad-hoc，`TeamIdentifier=not set` | 同上 |
| 公证 | **无**（未申请 Developer ID，未公证） | 同上 |
| Apple Silicon 原生 | **未构建、未验证** | 见 §7 |

Rosetta 2 下可运行 x86_64 版本，但**未在 Apple Silicon 实机验证**，本报告不作兼容性承诺。

---

## 3. 体积拆分（该产物的实测值，历史）

总计 963.7 MB（按文件字节；`du -sh` 显示 922 MiB）。

| 组件 | 体积 | 说明 |
| --- | --- | --- |
| Chromium headless shell 148.0.7778.96 | 188 MB | 特效导出（WebGL）用，随包分发 |
| OpenCV (`cv2`) | 149 MB | RapidOCR 图像预处理 |
| PyAV (`av`) | 146 MB | 自带 FFmpeg 共享库，faster-whisper 解码音频 |
| FFmpeg 7.1 CLI (`imageio_ffmpeg`) | 77 MB | MP4 封装/编码 |
| Whisper `tiny` 模型 | 78 MB | `Contents/Resources/assets/models/whisper-tiny` |
| ONNX Runtime | 68 MB | RapidOCR 推理 |
| CTranslate2 | 61 MB | faster-whisper 推理 |
| NumPy | 43 MB | 数值计算 |
| CPython 3.12 运行时 | 19 MB | `libpython3.12.dylib` |
| Pillow | 13 MB | Pillow 渲染路径 |
| tokenizers | 10 MB | Whisper 分词 |
| Noto Sans JP 变量字体 | 9.6 MB | 界面字体 + 日文回退 |
| `static/` + `webview` | 2.5 MB | 前端资源与 JS 桥 |
| 其余（pyobjc、pydantic、uvloop、httptools 等） | ≈110 MB | 运行时依赖 |

说明：`BUNDLE` 会把 `assets/**` 移到 `Contents/Resources/`，在
`Contents/Frameworks/assets/` 留下符号链接，因此 `du` 对这两处统计不一致；
上表按真实字节数统计，已去重。

---

## 4. 依赖清单

| 组件 | 是否打包 | 是否需联网 | 体积影响 | 许可 / 分发说明 |
| --- | --- | --- | --- | --- |
| CPython 3.12.14 | 是 | 否 | 19 MB | PSF |
| FFmpeg 7.1（`imageio_ffmpeg` 分发） | 是 | 否 | 77 MB | 见 `THIRD_PARTY_NOTICES.md`；许可取决于编译选项 |
| Pillow 12.2.0 | 是 | 否 | 13 MB | HPND/MIT-CMU |
| NumPy 2.5.4 | 是 | 否 | 43 MB | BSD-3 |
| OpenCV (`opencv-python` 4.10.0.84) | 是 | 否 | 149 MB | Apache-2.0 |
| pywebview 6.2.1 + pyobjc | 是 | 否 | ≈12 MB | BSD-3；WKWebView 属 macOS 系统组件 |
| FastAPI/Starlette/uvicorn/uvloop | 是 | 否 | ≈8 MB | BSD/MIT/Apache |
| Chromium `chrome-headless-shell` 148 | 是 | 否 | 188 MB | BSD-3；Chrome for Testing 带 Google 品牌，公开再分发可能需授权，详见 `assets/browser/README.md` |
| faster-whisper 1.2.1 | 是 | 否 | 小 | MIT |
| CTranslate2 4.8.3 | 是 | 否 | 61 MB | MIT |
| Whisper `tiny` 模型 | 是 | 否 | 78 MB | 随包分发，`assets/models/whisper-tiny` |
| ONNX Runtime 1.23.2 (CPU) | 是 | 否 | 68 MB | MIT |
| RapidOCR 1.4.4 + 内置模型 | 是 | 否 | 含于 onnxruntime 侧 | Apache-2.0 |
| PyAV 19.0.1 | 是 | 否 | 146 MB | BSD-3 |
| Noto Sans JP | 是 | 否 | 9.6 MB | SIL OFL 1.1（`assets/NotoSansJP-OFL.txt`） |
| 其他 Whisper 模型 | 否 | 是 | — | 用户在设置面板触发下载（Hugging Face） |
| Developer ID / 公证 | 否 | — | — | 未申请 |

所有导入路径均在冻结环境中验证可用：`test_phase2.py` 断言
`transcription runtime available`、`OCR runtime available`，并实际跑通推理，
而不是只做 import。

---

## 5. 功能矩阵（不安装任何外部软件）

| 功能 | 无 Chrome/Edge | 无 Homebrew | 断网 | 证据 |
| --- | --- | --- | --- | --- |
| 启动 / 原生窗口 | ✅ | ✅ | ✅ | `--smoke` 探测 + 验收第 1 项 |
| 中文 / 英文界面切换与持久化 | ✅ | ✅ | ✅ | 验收第 13–21 项 |
| 歌词导入 / 字幕编辑 / 逐词时间轴 | ✅ | ✅ | ✅ | 验收 + 动态控件断言 |
| 字体选择、自定义字体、CJK（含「词」）与日文回退 | ✅ | ✅ | ✅ | 离线帧 OCR `我们写下的词` 6/6 |
| Pillow 路径 MP4 导出 | ✅ | ✅ | ✅ | `offline-cjk (9).mp4`，H.264+AAC |
| WebGL / 特效 MP4 导出 | ✅（内置 Chromium） | ✅ | ✅ | 验收断言导出走包内浏览器路径 |
| Whisper 转写 | ✅ | ✅ | ✅ | 离线 `'Freshing writes words on the screen.'` |
| RapidOCR | ✅ | ✅ | ✅ | 离线 `我们写下的词日本語の卜` |
| 导出编码 H.264 + AAC | ✅ | ✅ | ✅ | `major_brand: isom`，ffprobe |
| 退出与进程清理 | ✅ | ✅ | ✅ | `threads still alive: none` |

内置浏览器解析顺序：`PHRASYNC_BROWSER` → 包内 `assets/browser/chrome-headless-shell-mac-<arch>/`
→ 系统 Chrome/Chromium/Edge。测试时设置 `PHRASYNC_REQUIRE_BUNDLED_BROWSER=1`，
强制禁止回退，从而证明导出确实用了包内运行时，而不是机器上已装的 Chrome。

该轮构建新增：包内浏览器目录名带架构后缀，由 `phrasync/webgl_renderer.py` 按 `platform.machine()`
选择，x86_64 包不会误用 arm64 运行时，反之亦然；`build_app.sh` 在构建前校验对应架构的
运行时存在，并拒绝在 Intel 上构建 arm64。

---

## 6. 测试结果（均针对该次交付包；历史记录，本次文档校正未重跑）

| # | 测试 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 完整验收套件（23 项，针对 `dist/Phrasync.app`） | **23/23 通过** | `.buildtest/phase2-final.log` |
| 2 | 中英双向字符串审计 | 通过，切回英文后中文残留 **0** | `.buildtest/i18n-p13.log`（静态资源哈希与最终包一致） |
| 3 | 断网离线验证（桌面副本） | **8/8 通过** | `.buildtest/offline-desktop.log` |
| 4 | 原生 WKWebView 窗口 + 中文 locale（桌面副本） | 通过 | `~/Library/Logs/Phrasync/launcher.log` 16:14:47–51 |
| 5 | 从桌面副本启动（非源码树） | 通过，端口顺延 | 同上 |
| 6 | 架构守卫拒绝跨架构构建 | 按预期拒绝（exit 2） | 见 §7 |

最终包的验收断言（日志原文）：最小环境启动 pid 14851、health `0.4.7`、
包内浏览器 `…/assets/browser/chrome-headless-shell-mac-x64/chrome-headless-shell`、
transcription runtime available、OCR runtime available、RapidOCR `我们写下的词`、
Whisper `'Freshing writes words on the screen.'`、特效导出完成、MP4 落在包外
`phase2-run/out/phase2 (11).mp4`、`major_brand: isom`（H.264+AAC）、中文界面
`工作室='工作台'`、`导出 MP4`、选择器 `['简体中文','English']`、持久化 `zh-CN`、
切回英文 `Studio`、歌词 `MAKE EVERY\nFRAME MOVE` 未被改写、动态控件
`['跳转到字幕','删除字幕','复制字幕']`、`4 条字幕`、干净退出、无残留服务。

桌面副本 smoke 关键值：`locale":"zh-CN"`、`ready":"complete"`、`scripts:29`、
`canvases:5`、`kinetic:"object"`、`viewport:[1480,912]`、`Threads still alive: none`。

### 中文化说明

界面文案以英文为源，`static/i18n-zh.js` 为字典，`static/i18n.js` 负责查表与反查，
`static/i18n-dom.js` 负责 DOM、动态控件、属性文本与后端消息的翻译。该轮修复的关键缺陷：中文态下 `t()` 会把
**译文**写入 DOM，导致英文原文丢失，切回英文时无法还原。现在每次本地化都会登记
「译文 → 英文源」，并配合字典反查表与动态句式反查（版本号、剩余时间、渲染帧计数等），
切回英文可完整还原。英文源记录不涉及歌词、导入字幕、文件名、字体名。

中文界面中仍显示英文的文本节点均为刻意保留：品牌（`PHRA`/`SYNC`/`PHRASYNC`/
`Phrasync`/`Giovanni De Miccoli`/`LinkedIn`/`GitHub`/`Microsoft Store`/`Hugging Face`）、
快捷键字形（`Ctrl+N · Ctrl+O · Ctrl+S`）、文件格式名（`WAV/MP3/FLAC/M4A`、`SRT/LRC/TXT`）、
单位与数值（`0 ms`、`60 ms`、`s`、`−20ms`、`+20ms`、`−0.1s`、`0.1s`、`1920 × 1080 · 30 fps`、
`A`、`Base`、`FPS`）、项目歌词内容（`MAKE`/`EVERY`/`FRAME`/`MOVE`，属内容不得翻译）、
以及 token 占位符 `hf_…`。无功能性遗漏。

---

## 7. 未验证 / 已知限制

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| 原生 arm64 构建 | **无法在本机构建，未验证** | 本机 `uname -m = x86_64`、`hw.optional.arm64` 不存在，Intel Mac 不能执行 arm64 代码；PyInstaller 不支持交叉编译；构建解释器 `cpython-3.12.14-macos-x86_64-none` 及全部原生依赖（CTranslate2、ONNX Runtime、OpenCV、PyAV、FFmpeg、Chromium）均为 x86_64 thin |
| arm64 构建流程 | 已脚本化，**待 Apple Silicon 实机执行** | `build_app.sh` 按 `uname -m` 自适应；`PHRASYNC_TARGET_ARCH=arm64` 在 Intel 上 exit 2。步骤见 `packaging/macos/README.md`「Building a native arm64 bundle」 |
| universal2 单包 | **不支持，未验证** | NumPy/OpenCV/ONNX Runtime/CTranslate2 只发 x86_64 或 arm64 独立 wheel，无 universal2 |
| Apple Silicon + Rosetta 2 实际运行 | **未验证** | 无 arm64 机器 |
| 公证 / Gatekeeper 放行 | **未做** | 未申请 Developer ID；跨机分发需右键打开或 `xattr -dr com.apple.quarantine` |
| 大模型（small/medium）离线转写 | **未打包** | 体积与许可权衡；仍在设置面板按需下载 |
| GPU 推理 | **不可用** | health 实测 `cuda: false`；本机无兼容 NVIDIA GPU |
| 双击（Finder）启动 | 沿用 Phase 1 结论 | 该轮用等价命令行 + 窗口 smoke 验证；未重复鼠标双击 |

---

## 8. 安装现状（该轮交付时的状态）

该轮交付时最终包已安装到桌面，旧版未保留（用户已删除）；本次文档校正未复核桌面副本是否仍在：

```bash
cp -Rc ~/phrasync/dist/Phrasync.app ~/Desktop/Phrasync.app   # 已完成，codesign -v 通过
```

桌面副本实测：`du -sh` 922 MiB、`963.7 MB`、1731 个文件条目，签名校验通过，
`--smoke` 与断网 8/8 均在**副本位置**完成，不依赖源码树。

用户数据不受影响：字体在 `~/Library/Application Support/Phrasync/fonts`，
工作区在 `~/.phrasync`（上传、项目、渲染、日志），升级不删除。

如需在 Apple Silicon 上原生运行，需在该机器上按 §7 与 README 的 arm64 流程重新构建；
当前 x86_64 包在 Apple Silicon 上通过 Rosetta 2 运行（未实测）。
