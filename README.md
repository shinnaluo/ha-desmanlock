# 德斯曼智能锁homeassistant集成

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=home-assistant-community-store&logoColor=white)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/v/release/shinnaluo/ha-desmanlock)](https://github.com/shinnaluo/ha-desmanlock/releases)

将德施曼智能锁接入 Home Assistant。集成通过德施曼云端接口获取门锁状态、开门记录及设备信息，并提供动态密码和数字密码管理服务。

### 实体

| 类型 | 实体 |
| --- | --- |
| 按钮 | 解锁（仅开锁，不会误触上锁） |
| 二元传感器 | 门锁状态（已解锁 / 已上锁 / 未知），附带状态来源与最近开门记录等属性 |
| 传感器 | 大电池电量、小电池电量、猫眼电量、电池状态、最近开门用户、开门方式、开门时间、开门日志、告警日志、操作日志、网络信号 |
| 诊断传感器 | Wi-Fi、网络模式、软件版本、指纹、人脸及门铃音量等信息 |
| 图像 | 安防抓拍 |

部分实体是否有值取决于门锁型号、硬件能力和云端返回的数据。

> [!NOTE]
> 本分支把上游的 `lock` 实体拆成了「解锁按钮 + 门锁状态二元传感器」。官方 App 未提供主动上锁指令，锁门依赖门锁自身的自动上锁机制，因此不再提供点了会报错的上锁开关。

## 本分支的变更（相对上游 v0.2.8）

| 变更 | 说明 |
| --- | --- |
| 移除 `lock.xxx` 实体 | 上游 `lock` 平台点「上锁」必定报错，本分支不再加载 `lock` 平台；升级时配置条目自动迁移（版本 2 → 3）并删除旧的实体注册项，不会留下灰色不可用实体。 |
| 新增 `button.desmanlock_<锁ID>_unlock` | 按下即通过蓝牙开锁，成功后立即刷新状态并请求一次云端刷新。 |
| 新增 `binary_sensor.desmanlock_<锁ID>_lock_state` | `device_class: lock`，开 = 已解锁，关 = 已上锁，无可用记录时为「未知」。附带 `lock_state`、`state_source`、最近开门用户/方式/时间、门锁 MAC、最近开锁指令时间等属性。 |
| 新增「解锁状态保持时间」选项 | 默认 30 秒，范围 0–600 秒；任何开锁事件只在这个窗口内视为「已解锁」，超时推定门锁已自动上锁。设为 0 会退回「按最新一条日志判断」的旧逻辑。 |
| 修正登录失败误报 | 上游把云端登录拒绝（如 `{"status":4,"msg":"密码错误"}`）误判为「无法连接或登录失败」。本分支区分「网络不可达」与「凭证被拒」，后者显示「账号或密码错误」，并在日志中以 warning 输出云端返回的原文与状态码。 |
| 修正门锁状态卡住 | 上游把「最新一条开锁日志」当作持续状态，用指纹/人脸/App 开锁后会长期显示「已解锁」。v0.3.2 改为按日志时间衰减，并加定时器在窗口到期时主动刷新实体；新增 `state_expires_at` / `state_is_inferred` 属性与更细的 `state_source` 取值便于自查。 |
| 版本号 | `0.3.2`。 |

**升级后需要改自动化**：原来调用 `lock.unlock` 的地方改为 `button.press`；原来读取 `lock.xxx` 状态的地方改为读取二元传感器。

```yaml
# 开锁
action: button.press
target:
  entity_id: button.desmanlock_123456_unlock

# 以「已解锁」作为自动化条件
condition: state
entity_id: binary_sensor.desmanlock_123456_lock_state
state: "on"
```

## 本仓库地址与更新检测

本仓库是 [chliny/ha-desmanlock](https://github.com/chliny/ha-desmanlock) 的个人 Fork，仓库地址为 `https://github.com/shinnaluo/ha-desmanlock`。以下链接均已指向本项目：

| 位置 | 依据 |
| --- | --- |
| Home Assistant 集成详情页的「文档」 | `manifest.json` → `documentation` |
| Home Assistant 集成详情页的「报告问题」 | `manifest.json` → `issue_tracker` |
| HACS「检查更新」、集成详情页「访问仓库」 | HACS 中登记的自定义存储库地址 |
| Release 与版本徽章 | 本仓库 Releases |

> [!IMPORTANT]
> 如果之前在 HACS 里添加的是上游 `chliny/ha-desmanlock`，请先到 **HACS → 右上角菜单 → 自定义存储库** 删除该条目，再重新添加 `https://github.com/shinnaluo/ha-desmanlock`（类别选「集成」）。否则 HACS 会继续去上游检查更新，把旧的 `lock` 实体装回来。

本仓库的 `hacs.json` 不再依赖 Release 附件，HACS 直接读取仓库中的 `custom_components/desmanlock` 内容，版本与更新提示均以本仓库为准。仓库自带的 Release 工作流会在推送 `v*` 标签时打包组件并创建 Release，也可在 GitHub 网页手动发布；当前 `v0.3.0` 已发布。

> [!NOTE]
> GitHub 对 Fork 仓库默认可能禁用 Actions。若打标签后没有自动生成 Release，到 **Actions** 页面启用一次即可；HACS 的更新检测本身不依赖该工作流。

## 安装

### 通过 HACS 安装（推荐）

1. 确保 Home Assistant 已安装 [HACS](https://hacs.xyz/docs/use/download/download/)。
2. 打开 HACS，进入 **集成**。
3. 打开右上角菜单，选择 **自定义存储库**。
4. 添加存储库地址 `https://github.com/shinnaluo/ha-desmanlock`，类别选择 **集成**。
5. 搜索并安装 **Desman Lock**。
6. 重启 Home Assistant。

后续版本可直接通过 HACS 的「检查更新」获取，来源始终是本仓库。

### 手动安装

1. 到 [本项目 Releases](https://github.com/shinnaluo/ha-desmanlock/releases) 下载最新版本，或直接克隆仓库 `git clone https://github.com/shinnaluo/ha-desmanlock.git`。
2. 将 `custom_components/desmanlock` 目录复制到 Home Assistant 配置目录下的 `custom_components`：

   ```text
   <config>/custom_components/desmanlock/
   ```

3. 确认目录中包含 `manifest.json`、`config_flow.py` 等文件。
4. 重启 Home Assistant。

## 配置

1. 进入 **设置 → 设备与服务**。
2. 点击 **添加集成**。
3. 搜索 **Desman Lock** 或 **德施曼智能锁**。
4. 输入德施曼账号手机号、密码和区域 ID。中国大陆账号通常保持默认区域 ID `1`。
5. 如果账号绑定了多把门锁，选择需要接入的门锁。再次添加集成并选择其他门锁，即可将同一账号下的多把门锁全部接入。
6. 在集成的「配置」选项中可调整「解锁状态保持时间」，默认 30 秒；设为 0 会关闭时间衰减，退回「按最新一条日志判断」的旧逻辑（不推荐）。

## 已知限制

- 依赖德施曼云端和网络连接，无法离线工作。
- 抓拍图片通过阿里云 Link Visual 接口获取临时地址，仅支持云端仍保留的图片。
- **门锁状态是事件推断值，不是物理读数**（`state_is_inferred: true`）：云端没有实时锁舌/门磁字段。显式「自动上锁」记录优先；其他开锁事件只在发生后「解锁状态保持时间」（默认 30 秒）内显示「已解锁」，到期自动回到「已上锁」。窗口到期由定时器主动刷新，无需等下一次 5 分钟云端轮询。`state_source` 标明依据：`cloud_auto_lock`、`cloud_unlock_recent`、`cloud_unlock_expired`、`unlock_in_progress`、`auto_lock_timeout`、`cloud_record*`（无法解析时间或时区不匹配时退回旧逻辑）、`unknown`。
- 蓝牙开锁要求 Home Assistant 主机（或支持主动连接的蓝牙代理）位于门锁通信范围内。
- 成功建立 GATT 连接后，集成会保持并复用该连接，直到门锁主动断开或集成卸载。
- 集成会读取门锁协议配置，并按 App 规则选择标准或 DH 密钥参数；ID2 安全芯片协议依赖厂商原生认证库，目前会明确返回不支持错误。
- App 协议只提供主动开锁；调用上锁会直接返回不支持错误。

### 为什么拿不到真实锁状态（抓包结论）

2026-11-09 用 Reqable 对德施曼 App 6.18.0 做过一次完整 HTTPS 抓包（142 条请求 / 61 秒，已脱敏），核对结论：

- `detailAndConfigV3` 的 `lockDetailInfo` 里有 `lockOpenStatus` 字段，但两次请求都是 `null`；`sleepStatus`、`doorUnclosedAlarmStatus`、`falseLockAlarmState` 都是配置或告警开关，不是实时锁舌/门磁读数。
- 全量抓包中**没有** `lockState` / `doorState` / `bolt` / `magnet` 一类实时状态字段，也没有 `api.link.aliyun.com` 的物模型属性查询（该域名本次 0 次请求）。
- 唯一接近实时事件的是 `/nyuwa/uc/getOfflineMessage` 的离线推送（`subMsgType=149`、标题「门锁已打开」），但它是通知消息，不是可查询的状态。
- App 首页根本不调用集成所用的开门日志接口 `/nyuwa/dc/lock/log/open/door/type`；云端日志按 300 秒轮询，而门锁开锁后几秒内就会自动上锁。

所以**无法从云端取得物理锁舌状态**，只能从事件推断。v0.3.2 的时间衰减解决了「状态长期卡在已解锁」，但仍不能保证与物理状态 100% 一致（门被挡住没锁上、云端日志延迟、HA 时区与门锁不一致等）。若 HA 时区与门锁不一致导致日志时间落在未来超过 5 分钟，`state_source` 会显示 `cloud_record_time_mismatch` 并自动退回旧逻辑，请检查 HA 时区设置。

## 故障排查

- 提示**「账号或密码错误」**：云端明确拒绝了登录。请先确认德施曼 App 能用「手机号 + 密码」登录（一直用短信验证码登录的账号可能没有设置密码，需先在 App 里设置）；检查有无多余空格、大小写，以及中国大陆账号的区域 ID 是否为 `1`。云端对不存在的手机号、错误密码、错误区域都统一返回「密码错误」，所以日志里只会有这一句。
- 提示**「无法连接德施曼云端」**：这才是真正的网络问题。检查 HA 容器能否解析并访问 `nyuwa.dsmxp.com`（Docker 版可用 `docker exec <容器名> curl -I https://nyuwa.dsmxp.com/` 测试）、DNS、代理和防火墙。
- **装完仍是 `0.2.8` / 表单只有 4 个字段**：说明 HACS 还在从上游 `chliny/ha-desmanlock` 下载。上游 `hacs.json` 带 `zip_release`，会拉取它 v0.2.8 Release 的 `desmanlock.zip`。请到 HACS → 右上角菜单 → 自定义存储库删除上游条目，重新添加本仓库并重启 HA；或直接用本仓库 Release 的 `desmanlock.zip` 覆盖 `<config>/custom_components/desmanlock`。判别方法：本分支的 `manifest.json` 有 `documentation` 字段且为 `0.3.2`，上游为空且为 `0.2.8`；本分支表单多一个「解锁状态保持时间」。
- 实体暂时不可用时，检查 Home Assistant 是否可以访问 `nyuwa.dsmxp.com`。
- 如需提交问题，请附上 Home Assistant 版本、集成版本、门锁型号和已脱敏的相关日志。请勿公开账号、密码、动态密码、数字密码、Token 或门锁 ID。

### 开启 Debug 日志

在 Home Assistant 中进入“设置 → 设备与服务 → 集成”，打开“德施曼智能锁”集成页面，在右上角菜单中选择“启用调试日志记录”。重新操作以复现问题后，再次打开菜单并选择“禁用调试日志记录”，Home Assistant 会自动下载调试日志文件。

也可以在 `configuration.yaml` 中添加以下配置并重启 Home Assistant：

```yaml
logger:
  logs:
    custom_components.desmanlock: debug
```

问题排查结束后，建议删除以上配置或将日志级别恢复为 `info`，避免产生过多日志。

## 免责声明

使用本集成产生的风险由使用者自行承担。请妥善保护 Home Assistant 实例及德施曼账号，尤其是在使用密码管理服务时。
