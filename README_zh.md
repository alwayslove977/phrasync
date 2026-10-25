<p align="center"><img src="docs/media/phrasync-mark.svg" alt="Phrasync" width="76"></p>

# Phrasync

[English](README.md) · **简体中文**

Phrasync 是一个免费、完全本地运行的歌词视频与字幕工作室。导入歌曲或视频，在本机完成转录，校对文字与时间轴，调整视觉样式，最后导出 MP4。媒体文件不会被上传到任何 Phrasync 服务。

原作者为 [jaydemks](https://github.com/jaydemks)。本文件描述的是
**[alwayslove977/phrasync](https://github.com/alwayslove977/phrasync)** 的
`macos-fixes` 分支，也就是这个 fork 的 macOS 维护版本。

> ### 关于本仓库的 macOS 构建
>
> 当前版本 **0.4.7**，把上游源码打包成可双击运行的 `Phrasync.app`，并修复了让上游代码无法作为独立 macOS 应用运行的缺陷。
>
> - **非官方发布**：不是 jaydemks 的官方版本。
> - **没有 Developer ID 签名，也没有公证（notarization）**，只有 PyInstaller 的 ad-hoc 签名。
> - 已发布的包 **仅支持 Intel（x86_64）**。
> - 下载：[Releases — v0.4.7-macos.1](https://github.com/alwayslove977/phrasync/releases/tag/v0.4.7-macos.1)。
> - 构建细节与全部改动清单：[`packaging/macos/README.md`](packaging/macos/README.md) 与 [`docs/MACOS_FIXES.md`](docs/MACOS_FIXES.md)。

## 功能概览

**歌词视频**：导入歌曲，用本地转录或直接粘贴/导入歌词，然后按波形逐句、逐字对时间。文字可选 2D 动态排版或穿过场景的 3D 文字；背景可用静态图片、循环视频、随音频反应的背景，或 Odyssey 3D 场景（日本、意大利、中国、美国，以及 Lost in the Ocean），并提供镜头运动、时段、天气和美术方向控制。

**字幕视频**：导入视频或音频，生成可编辑字幕并压制进 MP4。同一个视频可以同时作为转录来源、预览画面和最终的音视频素材。

两种模式下都可以：

- 修改文字、增删字幕行、用拖动／吸附／微调／击拍同步／自动对齐调整词句时间。
- 用媒体箱搭建画面：把图片、视频和内置 2D/3D 视觉素材拖到最多四条背景轨，支持移动、裁剪、分割、复制、透明度与转场，以及平移/缩放动画。
- 添加黑白、渐变、粒子、音频频谱等效果，并用节拍或检测到的瞬态触发抖动、钟摆、闪光、缩放与光脉冲。
- 用 **I/O**、时间轴标记或精确秒数设定导出区间，只渲染需要的片段。
- 本地 Faster-Whisper 转录，支持自动语言检测；Windows 上可选 NVIDIA CUDA 加速，macOS 构建为 CPU 推理。
- 导入歌词或字幕，用 OCR 从图片提取文字，导出 SRT、WebVTT、LRC、逐词 LRC 与 ASS 卡拉 OK 字幕。
- 预览、保存/重新载入本地工程、运行预检，导出 H.264 MP4。
- 打开 **Diagnostics** 查看错误信息，便于反馈问题。

**界面语言**：默认英文，右上角语言按钮可在 **English / 简体中文** 之间切换，选择会被记住。上游默认的意大利语在本 fork 中替换为简体中文（见 `docs/MACOS_FIXES.md`）。歌词正文、导入的字幕、文件名、字体名和导出的字幕内容不参与界面翻译。

## 系统与硬件要求

| 项目 | 要求 |
| --- | --- |
| 系统版本 | **macOS 12.0 及以上**。按本分支构建的包在 `Info.plist` 里声明 `LSMinimumSystemVersion` = **12.0**（AI 包开关不改变该值），取自包内非 OCR 原生依赖的 load command 实测值。**OCR 依赖要求 13.4，因此在 12.0–13.3 上 OCR 不保证可用**，其余功能不受影响 |
| 架构 | **x86_64（Intel）**；Apple Silicon 需通过 Rosetta 2 运行 |
| 磁盘 | 应用解压后约 **922 MiB**（zip 包 392.8 MiB），另需留出工程与导出视频的空间 |
| 其他 | 不需要预装 Python、Homebrew、Chrome 或 Edge |

关于版本号的说明很重要：对已发布包内全部 550 个 Mach-O 文件执行 `vtool -show-build` 的结果是：371 个文件要求 12.0（`av`、numpy 及多数扩展模块），4 个文件要求 13.4（OCR 使用的 ONNX Runtime 1.23.2）。dyld 不会加载最低版本高于当前系统的库，所以低于 12.0 的系统连核心扩展都导入不了。原先构建配置把这些一律写成 11.0，**这个声明并不成立**。

现在构建配置声明 **12.0**：这是包内**非 OCR** 原生依赖的最高要求。13.4 只属于 ONNX Runtime，而唯一导入它的是 `phrasync/ocr.py`——该导入是惰性的、包在 `except Exception` 里，失败时先回落 Tesseract，仍不可用才抛 `OCRUnavailable`，并由 `/api/health` 把原因报到界面上。因此 12.0 上除 OCR 外的功能都可运行，**只有 OCR 不保证可用**；如果按 13.4 声明整个包，会把 12.0–13.3 的机器挡在一个只缺 OCR 的应用之外。`--no-ai` 构建同为 12.0。

注意**已经发布的 0.4.7 压缩包是在这次修正之前构建的**，它的 `Info.plist` 里仍然是 11.0，请按 12.0 对待（OCR 另需 13.4）。这些数字来自 Mach-O 的 load command，**不是在 12.x / 13.x 实机上启动验证的结果**。

## 下载与安装（macOS）

1. 从 [Releases](https://github.com/alwayslove977/phrasync/releases/tag/v0.4.7-macos.1) 下载 `Phrasync-0.4.7-macos-x86_64.zip`。
2. 解压，把 `Phrasync.app` 拖进 `/Applications`（或任意你拥有写权限的位置）。
3. **首次启动前需要处理隔离标记**：

   ```bash
   xattr -dr com.apple.quarantine /Applications/Phrasync.app
   ```

   然后正常双击启动。若跳过这一步，Gatekeeper 只会在警告框里提供“完成”，不会给你“打开”。

### 关于签名与这一步的风险

- ad-hoc 签名**不等于** Developer ID 签名，也**不等于**公证。ad-hoc 只表示包内文件自洽（`codesign --verify --deep --strict` 会通过），不表示 Apple 或任何可信第三方为它背书。
- 上面的 `xattr` 命令会**移除该应用的隔离标记**，等于对这一份应用关闭 Gatekeeper 的下载来源检查。只应对你自己构建、或从你信任的来源获取、并核对过校验值的包这样做。
- 本次发布包的 SHA-256：`dfee7c54c6931b4b55b676569e2fb72d0ace2a0846bebecc5054d205aad1ffdd`。下载后可自行核对：

  ```bash
  shasum -a 256 ~/Downloads/Phrasync-0.4.7-macos-x86_64.zip
  ```

- 如果你是在本机自行构建、或者用 `cp -Rc`（APFS clone）而不是 `ditto` 拷贝到桌面，通常不会带上隔离标记，也就不需要上面这一步。`ditto` 会把 PyInstaller 的共享库符号链接展开成真实副本，体积大约翻倍。
- 想要去掉这些限制，只能由持有 Apple Developer ID 证书的人重新签名并提交公证，这不在本 fork 的能力范围内。

### 首次启动会发生什么

启动器会在 5500 起的第一个空闲本地端口上启动服务，轮询 `/api/instance` 确认接口真正可用，然后用 WKWebView 打开原生窗口。再次双击不会启动第二个服务，而是复用已在运行的实例。若原生窗口创建失败，会用原生弹窗提示并在默认浏览器中打开编辑器。

**首次启动不需要联网**：运行时、FFmpeg、OCR 模型和 Whisper `tiny` 模型都已在包内。

## 从源码运行

需要 **Python 3.10 或更高**（`scripts/install_unix.sh` 会依次尝试 `python3.12`、`python3.11`、`python3.10`、`python3`）。

```bash
git clone https://github.com/alwayslove977/phrasync.git
cd phrasync
git checkout macos-fixes

./run_macos.command          # 首次会自动执行 scripts/install_unix.sh 建 .venv
# 或者手动：
./scripts/install_unix.sh
.venv/bin/python app.py
```

`app.py` 的常用参数：

| 参数 | 作用 |
| --- | --- |
| `--external-browser` | 在系统默认浏览器中打开编辑器，而不是内嵌窗口 |
| `--port N` | 指定端口（默认 5500 起） |
| `--no-browser` | 只启动服务，不打开界面 |
| `--reload` | 开发模式，代码改动后自动重载 |

依赖分两层：`requirements.txt` 是运行必需；`requirements-ai.txt` 是可选的本地 AI 包（faster-whisper、RapidOCR、ONNX Runtime 等）。`scripts/install_unix.sh` 会先装核心依赖，AI 包失败时不会中断安装，可稍后用 `scripts/install_ai_unix.sh` 重试。macOS Intel 上 `requirements-ai.txt` 对 `onnxruntime` 和 `opencv-python` 有版本上限，这是因为这两个包的新版本已不再提供 macOS x86_64 的预编译轮子。

## 构建 `.app`

构建需要两个**不随仓库提交**的大文件（`.gitignore` 已屏蔽，`build_app.sh` 会在构建前检查并报告缺失）：

```bash
# 1) 导出用的 Chromium（约 195 MB）
python3 -m venv .venv-tools && .venv-tools/bin/pip install playwright
.venv-tools/bin/playwright install chromium-headless-shell
mkdir -p assets/browser/chrome-headless-shell-mac-x64
cp -R ~/Library/Caches/ms-playwright/chromium_headless_shell-*/. \
      assets/browser/chrome-headless-shell-mac-x64/

# 2) 随包分发的 Whisper tiny 模型（约 75.5 MB）
.venv-tools/bin/pip install huggingface_hub
.venv-tools/bin/hf download Systran/faster-whisper-tiny \
  --revision d90ca5fe260221311c53c58e660288d3deb8d356 \
  --include "config.json" "model.bin" "tokenizer.json" "vocabulary.txt" \
  --local-dir assets/models/whisper-tiny
```

然后：

```bash
packaging/macos/build_app.sh        # 完整干净构建
packaging/macos/build_app.sh --fast # 复用构建用 venv，跳过 --clean
```

- 输出：`dist/Phrasync.app`；日志：`build/macos/logs/build-<时间戳>.log`。
- 打包后自检：`dist/Phrasync.app/Contents/MacOS/Phrasync --smoke`（打开真实窗口，3 秒后执行 DOM 探针并输出 `SMOKE {...}`）。
- 构建脚本在打包后会校验 bootloader、`Info.plist`、`static/index.html`、字体、随架构匹配的导出用浏览器、Whisper 模型，以及按 `ffmpeg-*` 通配符匹配的 FFmpeg 二进制；缺任何一项都会以非零状态退出。

`build_app.sh` 与 `build_app.py` 是同一套流程的两种驱动（后者用于 shell 无法写 `/var/tmp` 的账号）。`Phrasync.spec` 还会把 `static/` 下的历史备份文件与 `.DS_Store` 排除出包，并校验七个 AI 包是否真的收集到了各自必需的原生库／数据／隐藏导入。

## 主要使用流程

**歌词视频**：导入歌曲 → 选择转录语言策略（`auto` 跟随歌曲自动判断语言切换，`multilingual` 始终按语言切分，`single` 锁定单一语言）→ 校对各句与逐词时间 → 选择 2D/3D 排版与背景 → 预览 → 导出 MP4。

**字幕视频**：导入视频 → 生成字幕并编辑 → 需要时用 OCR 从画面或图片补文字 → 导出字幕文件（SRT / WebVTT / LRC / 逐词 LRC / ASS）或直接压制成 MP4。

**导出**：用 **I/O** 键、时间轴标记或精确秒数设定 IN/OUT，选择导出目录与码率后渲染。导出视频只会写入你在对话框里选择的目录，不会写进应用包内。长视频和高分辨率导出会占用可观的 CPU 时间与磁盘空间。

**上传上限**：默认单个文件最大 16 GB（由 `MAX_UPLOAD_MB` 环境变量控制，默认 16384）。

## AI 模型与联网行为

- 随包分发：Whisper `tiny` 模型，因此开箱即可离线转录。
- 按需下载：在设置面板选择 `tiny` 以外的模型时，会从 Hugging Face 下载到本机；下载进度、体积和剩余时间会在界面中显示。这是唯一需要联网的功能（以及首次从源码安装依赖时）。
- 可选凭证：设置面板可以填 Hugging Face access token，用于下载受限模型。该 token 会以**明文**写入 `~/.phrasync/settings.json` 的 `huggingFaceToken` 字段，也可以改用环境变量 `HF_TOKEN`。不需要时请点“移除”。
- 你的音频、视频、歌词都不会被上传：转录和渲染全部在本机完成。

## 测试

```bash
# 安装开发依赖（含 pytest、httpx、pyinstaller）
python -m pip install -r requirements-dev.txt

python -m pytest                       # 运行 tests/ 下全部用例
python -m pytest tests/test_build_scripts.py -q
```

`scripts/run_tests_unix.sh` 会创建/激活 `.venv`、安装开发依赖并运行整套测试。

与本 fork 的 macOS 改动直接相关的用例：

| 文件 | 覆盖内容 |
| --- | --- |
| `tests/test_build_scripts.py` | 两个构建驱动的退出码、必需资源校验、spec 的数据过滤与 AI 资源下限，以及 `install_wheels.py` 的路径穿越防护 |
| `tests/test_i18n_ui.py` + `tests/i18n_ui.cjs` | 简体中文界面与英文回切 |
| `tests/test_frontend.py` | 前端模块行为 |
| `tests/test_cue_pagination.py` | 字幕行分页 |

构建相关的测试不需要真正打包：它用桩对象执行真实的 `Phrasync.spec` 与两个驱动，几秒钟内即可断言退出码与收集结果。

## 常见问题与故障排查

| 现象 | 原因与处理 |
| --- | --- |
| 双击后提示“无法打开，因为 Apple 无法检查其是否包含恶意软件” | 未签名/未公证导致的隔离标记。核对 SHA-256 后按上文执行 `xattr -dr com.apple.quarantine`；或在 Finder 中右键 → 打开 |
| 提示“应用已损坏，无法打开” | 多为拷贝过程中符号链接被展开（用了 `ditto`）或下载不完整。重新解压原始 zip，必要时用 `cp -Rc` 拷贝 |
| 首次转录卡在下载 | 该模型不在包内时会从 Hugging Face 下载；检查网络，或在设置里改用已随包分发的 `tiny` |
| OCR 按钮不可用 | 用的是 `--no-ai` 构建（包内没有 ONNX Runtime），或系统低于 13.4。界面状态栏会给出具体原因：包内缺少引擎时提示安装 AI 包，引擎已安装但加载失败时提示需要 13.4。可另装 Tesseract（`brew install tesseract`）作为替代引擎 |
| 端口被占用 | 启动器会自动尝试下一个空闲端口；也可用 `--port N` 指定 |
| 重复双击出现多个窗口 | 正常情况会复用已运行实例；若上一实例异常退出，检查 `~/Library/Logs/Phrasync/launcher.log` |
| 导出失败或没有画面 | 先运行 Diagnostics 看错误；源码环境下确认 `assets/browser/` 存在，打包环境下确认包内带有匹配架构的 `chrome-headless-shell` |
| 中文界面没有生效 | 右上角语言按钮切换；选择记录在浏览器本地存储中，歌词正文本身不会被翻译 |

日志位置：启动器 `~/Library/Logs/Phrasync/launcher.log`，应用 `~/.phrasync/logs/phrasync.log`。

## 隐私与数据存储

应用本身不收集数据、不上报统计，也没有账号体系。所有可写数据都在应用包之外：

| 数据 | 位置 |
| --- | --- |
| 工作区（上传、工程、渲染产物、任务、日志） | `~/.phrasync` |
| 自定义字体 | `~/Library/Application Support/Phrasync/fonts` |
| 设置（含可选的 Hugging Face token） | `~/.phrasync/settings.json` |
| 启动器日志 | `~/Library/Logs/Phrasync/launcher.log` |
| 支持日志 | `~/.phrasync/logs/phrasync.log` |
| WKWebView 存储 | `~/Library/Application Support/Phrasync/WebKit` |

工程文件只记录本地媒体的路径，不内嵌源文件；迁移工程时请连同媒体一起移动。替换或删除应用不会影响上述目录。

## 第三方组件与许可证

本项目以 **Apache-2.0** 许可发布，见 [`LICENSE`](LICENSE)。再分发时请保留 [`NOTICE`](NOTICE) 与 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。你创作出来的视频归你所有，但仍受你所用音乐、歌词、素材、图片和字体的授权约束。

已发布包内含：

| 组件 | 说明 |
| --- | --- |
| CPython 3.12 运行时 | `Contents/Frameworks/libpython3.12.dylib` |
| FFmpeg 7.1 | 用于 MP4 封装与音频解码 |
| Chromium headless shell（Chrome for Testing 148） | 仅用于效果导出，许可证与品牌说明见 `assets/browser/README.md` |
| faster-whisper + CTranslate2 | 本地转录，CPU 推理 |
| ONNX Runtime + RapidOCR | OCR，模型随包 |
| Pillow / NumPy / OpenCV | 渲染与图像处理 |
| pywebview / WKWebView | 原生窗口 |
| Noto Sans JP 可变字体 | 界面中日文字形 |

## Intel 与 Apple Silicon

- 当前发布包是**瘦 x86_64**（`Mach-O thin (x86_64)`），在 Intel Mac 上原生运行，在 Apple Silicon 上通过 **Rosetta 2** 运行。
- Rosetta 2 路径**没有在 arm64 硬件上实际验证过**，属于“应该可用但未测试”。
- PyInstaller 无法交叉编译：bootloader 和所有原生扩展都来自构建解释器。在 Intel 机器上构建 arm64 包会被 `build_app.sh` 拒绝。
- 在 Apple Silicon 上原生构建需要：arm64 的 CPython 3.12、arm64 的 `assets/browser/chrome-headless-shell-mac-arm64/`，然后 `packaging/macos/build_app.sh --fast`。步骤与清单见 [`packaging/macos/README.md`](packaging/macos/README.md) 的 “Building a native arm64 bundle” 一节。
- `universal2` 构建目前**不成立**：NumPy、OpenCV、ONNX Runtime、CTranslate2 都只发布分架构的轮子。

## 许可与致谢

Phrasync 由 [jaydemks](https://github.com/jaydemks) 创建并开源（Apache-2.0）。本 fork 只做 macOS 打包与兼容性修复，不是官方发行版。
