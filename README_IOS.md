# Artemis 独立工程（含 iOS 接入）

本目录保留上游 Git 历史及当前 iOS 修改。源码在 `artemis/`，界面源码在
`artemis/drivers/ios/console.html`，运行脚本在 `scripts/`。
原调研目录和已有旧版 `ChatGPT/artemis` 工程均未删除或覆盖。

## 启动

先启动指定设备的 WebDriverAgent，然后运行：

```sh
sh scripts/artemis-ios.sh ui --device-id <UDID> --wda-url http://127.0.0.1:8100 --port 8011
```

命令行任务：

```sh
sh scripts/ios-agent.sh --model gemini --profile flash --device-id <UDID> --wda-url http://127.0.0.1:8100 --goal '打开设置并验证标题，不修改设置'
```

当前专用模拟器 UDID：`F82C65F7-6DA6-4108-AB46-F54742E1C049`。
模型配置为本工程 `.env.ios`（不入 Git）和 `config/ios-models.json`。
模型选择支持 Gemini、Qwen API。`.venv` 是本目录单独建立的环境。

WDA 源码在 `.cache/WebDriverAgent`。模拟器重新启动 WDA：

```sh
xcodebuild -project .cache/WebDriverAgent/WebDriverAgent.xcodeproj -scheme WebDriverAgentRunner -destination 'platform=iOS Simulator,id=F82C65F7-6DA6-4108-AB46-F54742E1C049' -derivedDataPath .cache/wda-build CODE_SIGNING_ALLOWED=NO test
```

不需要原调研目录即可重建和运行。已有 WDA 服务也可通过 URL 连接。
真机部署见 [iOS 接入文档](docs/ios-integration.md)。

## USB 真机入口

```sh
# 只列真机；分别显示 USB 在线、开发隧道、配对和开发者模式
sh scripts/artemis-ios.sh devices
# 在已完成签名配置的设备上启动 WDA（持续运行）
sh scripts/ios-wda-device.sh <UDID> <TEAM_ID>
# 另一个终端：管理 USB 转发并启动真机控制台
sh scripts/artemis-ios.sh usb-ui --device-id <UDID>
```

真机控制台默认 http://127.0.0.1:8012，USB 转发默认 8101 → 设备 8100，
与模拟器 8011/8100 分开。退出控制台会关闭它启动的转发进程。
未连接 USB 或 WDA 未就绪会明确报错，不会回退连接模拟器。
8000 原生页面也已支持 iOS，见下面的原生入口。

## 8000 原生入口

在 `http://127.0.0.1:8000/` 顶部选择 **iOS · iPhone / iPad**，在系统设置中刷新设备列表，
选择 USB 真机或已启动的 iPhone / iPad 模拟器，填写该设备的 WDA 地址，连接设备。
真机的 WDA 必须已用 Xcode 签名启动，并保持 USB 转发运行（默认 `http://127.0.0.1:8101`）。
模拟器可使用独立端口，无需 USB 转发：

```sh
sh scripts/ios-wda-simulator.sh <simulator-UDID> 8102
```

选择该模拟器并填写 `http://127.0.0.1:8102`。连接时会检查 WDA 的真机/模拟器及 iPhone/iPad 类型。

连接后可在原生首页提交 Flash / Pro 任务，在 Workspace 查看执行日志、结果和步骤截图。
连接面板提供实时画面预览；任务执行期间也可以打开 Workspace 的实时画面。
模型使用原生 `.env` 和 `config/artemis.jsonc`，不再读取独立控制台的 `.env.ios`。
设备选择保存在忽略 Git 的 `.cache/dashboard-device.json`；任务提交时固定 UDID 和 WDA 地址，
等待中或执行中的任务结束前不能切换设备。任务取消复用原生队列与 SDK 清理流程。
iOS 暂不提供视频录制、APK 安装和 Android 应用锁定。

2026-10-21 已通过 8000 原生页面在 USB iPhone 上完成 Gemini Flash 设置页标题验证，
Workspace 正常展示完成结果及一步截图回放。该验证不代表所有 Pro 场景均已覆盖。

2026-10-21 已通过 8000 原生页面在 iPad Pro 11-inch (M5)、iPadOS 26.5 模拟器上完成
Gemini Flash 验证：打开设置 → 通用 → 关于本机，读取系统版本和型号，三步完成，截图回放正常。
会话：`532b7eb5-e511-4d7e-8bf9-c5554edff272`。iPad 真机尚未验证。

Task Queue 保存运行历史；Notes & Plans 只显示所选会话实际保存的笔记和计划文件。
Flash 可以完成任务而不生成这些文件；最终结果与步骤回放仍在任务详情中。Pro 会使用结构化规划。

## 界面语言

8000 原生首页右上角可切换「简体中文 / English」，偏好保存在当前浏览器并同步到工作区。
首次访问根据浏览器语言选择。中文模式的新任务会附加中文结果、笔记与计划的输出偏好，
任务明确要求的语言优先；已有日志、用户内容、技术标识和未识别的底层错误保留原文。
翻译词条位于 `apps/showcase_ui/src/app/i18n/zh-cn.ts`，模板用 `t` 管道显式标记界面文案。
8011 / 8012 独立控制台不使用此语言设置。
