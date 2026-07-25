# RDK X5 Hardware Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让现有 Next.js 网站读取 RDK X5 上 DHT11 的真实温湿度，并通过同一套 `HardwareDriver` 控制四颗 LED，同时保留模拟器和明确的离线降级。

**Architecture:** RDK X5 运行一个只依赖 Python 标准库和 `Hobot.GPIO` 的常驻 HTTP 服务，DHT11 由已验证的 `libgpiod` C 工具采样；Next.js 新增 `RdkX5Driver` 调用该服务。运行时不反复建立 SSH，SSH 仅用于部署、启动和诊断。

**Tech Stack:** Next.js 16、TypeScript、Vitest、Python 3 标准库、Hobot.GPIO、libgpiod、systemd、SQLite、StepFun API。

## Global Constraints

- 业务代码只依赖 `HardwareDriver`，不得出现 RDK X5 GPIO 分支。
- `HARDWARE_DRIVER=rdk-x5` 才启用实机；默认保持 `SimDriver`。
- DHT11 使用物理 Pin 11；LED 使用白 13、黄 15、蓝 18、红 22，共地 Pin 20。
- `warm` 为黄灯主、红灯辅；`cool` 为蓝灯主、白灯辅；亮度限制 0-100。
- 光照没有传感器时必须返回 `lightSource: "estimated"`，不得称为实测。
- StepFun Key 只读服务端环境变量 `STEPFUN_API_KEY`，密码和密钥不得提交。
- MAX30102 与真实空调执行器不在本计划范围内。
- 新行为遵循 RED-GREEN-REFACTOR；每个任务独立验证。

---

## File Map

- `hardware/rdk-x5/hardware_agent.py`：板端状态、DHT11 子进程、灯光映射和 HTTP API。
- `hardware/rdk-x5/test_hardware_agent.py`：不接 GPIO 的板端单元测试。
- `hardware/rdk-x5/dht11_read.c`：已验证的 DHT11 `libgpiod` 读取程序。
- `hardware/rdk-x5/baby-good-sleep-hardware.service`：systemd 服务定义。
- `hardware/rdk-x5/install.sh`：可重复执行的板端安装脚本。
- `lib/hardware/rdk-x5.ts`：网站端 `RdkX5Driver`。
- `lib/hardware/rdk-x5.test.ts`：HTTP 契约、超时和缓存测试。
- `lib/hardware/index.ts`：按环境变量选择驱动。
- `lib/hardware/index.test.ts`：驱动选择测试。
- `lib/hardware/driver.ts`：环境读数元数据类型。
- `app/api/env/route.ts`：返回健康状态并处理冷启动离线。
- `components/DashboardClient.tsx`：展示实机、估算光照和离线状态，隐藏实机下的造场入口。
- `components/SleepingClient.tsx`：在巡检失败时明确提示硬件连接状态。
- `.env.example`：公开配置名，不包含密钥值。
- `hardware/rdk-x5/README.md`：接线、部署、诊断和验收命令。

### Task 1: Board Hardware Agent

**Files:**
- Create: `hardware/rdk-x5/test_hardware_agent.py`
- Create: `hardware/rdk-x5/hardware_agent.py`
- Create: `hardware/rdk-x5/dht11_read.c`

**Interfaces:**
- Produces: `HardwareController.read_environment() -> dict`
- Produces: `HardwareController.set_light(on: bool, brightness: float, color_temp: str) -> dict`
- Produces HTTP: `GET /health`, `GET /environment`, `POST /light`

- [ ] **Step 1: Write failing light-mapping tests**

```python
def test_warm_light_uses_yellow_and_red_only():
    controller = HardwareController(FakeGPIO(), lambda: SENSOR_READING)
    result = controller.set_light(True, 20, "warm")
    assert result["channels"] == {
        "white": 0.0, "yellow": 20.0, "blue": 0.0, "red": 7.0,
    }

def test_brightness_is_clamped():
    controller = HardwareController(FakeGPIO(), lambda: SENSOR_READING)
    assert controller.set_light(True, 140, "cool")["brightness"] == 100
```

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest hardware/rdk-x5/test_hardware_agent.py -v`
Expected: FAIL because `hardware_agent` does not exist.

- [ ] **Step 3: Implement minimal controller and HTTP handler**

```python
PIN_BY_COLOR = {"white": 13, "yellow": 15, "blue": 18, "red": 22}

def light_channels(on, brightness, color_temp):
    level = min(100.0, max(0.0, float(brightness))) if on else 0.0
    if color_temp == "cool":
        return {"white": round(level * 0.35, 1), "yellow": 0.0,
                "blue": level, "red": 0.0}
    return {"white": 0.0, "yellow": level,
            "blue": 0.0, "red": round(level * 0.35, 1)}
```

The controller owns PWM instances, applies the returned duty cycles, keeps the last valid sensor reading, and returns `stale: true` only after a failed read. The HTTP handler validates JSON types and returns JSON errors with 400/503 status codes.

- [ ] **Step 4: Add stale-reading and HTTP contract tests**

```python
def test_sensor_failure_returns_last_value_as_stale():
    readings = iter([SENSOR_READING, RuntimeError("checksum")])
    controller = HardwareController(FakeGPIO(), lambda: next(readings))
    assert controller.read_environment()["stale"] is False
    assert controller.read_environment()["stale"] is True

def test_estimated_lux_tracks_brightness():
    controller = HardwareController(FakeGPIO(), lambda: SENSOR_READING)
    controller.set_light(True, 12, "warm")
    assert controller.read_environment()["lightLux"] == 122
```

- [ ] **Step 5: Verify GREEN**

Run: `python3 -m unittest hardware/rdk-x5/test_hardware_agent.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Version the verified DHT11 reader**

Copy the existing tested implementation without behavioral changes. Compile gate:

```bash
gcc -O2 hardware/rdk-x5/dht11_read.c -lgpiod -o /tmp/dht11-read
/tmp/dht11-read --help
```

Expected: usage identifies physical Pin 11 and `/dev/gpiochip4` line 1.

- [ ] **Step 7: Commit**

```bash
git add hardware/rdk-x5/hardware_agent.py hardware/rdk-x5/test_hardware_agent.py hardware/rdk-x5/dht11_read.c
git commit -m "feat: add RDK X5 hardware agent"
```

### Task 2: Next.js RdkX5Driver

**Files:**
- Create: `lib/hardware/rdk-x5.test.ts`
- Create: `lib/hardware/rdk-x5.ts`
- Modify: `lib/hardware/driver.ts`

**Interfaces:**
- Consumes: `GET /environment`, `GET /health`, `POST /light`
- Produces: `class RdkX5Driver implements HardwareDriver`
- Produces: optional `EnvReading.stale`, `EnvReading.lightSource`, `EnvReading.sampledAt`

- [ ] **Step 1: Write failing HTTP contract tests**

```ts
it("maps the agent environment response", async () => {
  const driver = new RdkX5Driver({
    baseUrl: "http://rdk:8765",
    fetchFn: async () => Response.json({
      tempC: 26.2, humidityPct: 63.5, lightLux: 122,
      lightSource: "estimated", stale: false, sampledAt: "2026-07-25T00:00:00Z",
    }),
  });
  expect(await driver.readEnvironment()).toMatchObject({ tempC: 26.2, humidityPct: 63.5 });
});

it("posts normalized light commands", async () => {
  const requests: RequestInit[] = [];
  const driver = new RdkX5Driver({
    baseUrl: "http://rdk:8765",
    fetchFn: async (_url, init) => { requests.push(init ?? {}); return Response.json({ ok: true }); },
  });
  await driver.setLight({ on: true, brightness: 120, colorTemp: "warm" });
  expect(JSON.parse(String(requests[0].body))).toEqual({ on: true, brightness: 100, colorTemp: "warm" });
});
```

- [ ] **Step 2: Verify RED**

Run: `npx vitest run lib/hardware/rdk-x5.test.ts`
Expected: FAIL because `RdkX5Driver` does not exist.

- [ ] **Step 3: Implement minimal driver**

```ts
export class RdkX5Driver implements HardwareDriver {
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;
  private readonly timeoutMs: number;
  private lastReading: EnvReading | null = null;
  private targetTempC: number | null = null;
  private lastAudio: AudioCmd | null = null;

  constructor(options: { baseUrl: string; fetchFn?: typeof fetch; timeoutMs?: number }) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.fetchFn = options.fetchFn ?? fetch;
    this.timeoutMs = options.timeoutMs ?? 3_000;
  }

  async readEnvironment(): Promise<EnvReading> {
    try {
      const response = await this.request("/environment");
      const reading = parseEnvironment(await response.json());
      this.lastReading = reading;
      return reading;
    } catch (error) {
      if (this.lastReading) return { ...this.lastReading, stale: true };
      throw new HardwareUnavailableError("RDK X5 环境传感器不可用", { cause: error });
    }
  }

  async setLight(cmd: LightCmd): Promise<void> {
    await this.request("/light", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        on: cmd.on,
        brightness: Math.min(100, Math.max(0, cmd.brightness)),
        colorTemp: cmd.colorTemp === "cool" ? "cool" : "warm",
      }),
    });
  }

  async health() {
    try { await this.request("/health"); return { ok: true, driver: "rdk-x5" as const }; }
    catch { return { ok: false, driver: "rdk-x5" as const }; }
  }

  async setClimate(cmd: { targetTempC: number }): Promise<void> {
    this.targetTempC = cmd.targetTempC;
  }

  async playAudio(cmd: AudioCmd): Promise<void> {
    this.lastAudio = cmd;
  }

  private async request(path: string, init: RequestInit = {}): Promise<Response> {
    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      ...init,
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!response.ok) throw new Error(`RDK X5 agent returned ${response.status}`);
    return response;
  }
}
```

Add `parseEnvironment(value: unknown): EnvReading` beside the class. It accepts only an object with finite `tempC`, `humidityPct`, and `lightLux`, `lightSource === "estimated"`, boolean `stale`, and string `sampledAt`. A failed read may return cached data with `stale: true`; a cold-start failure throws `HardwareUnavailableError`.

- [ ] **Step 4: Add timeout, invalid payload and cache tests**

```ts
it("returns cached data as stale after a transient failure", async () => {
  let fail = false;
  const driver = new RdkX5Driver({ baseUrl: "http://rdk:8765", fetchFn: async () => {
    if (fail) throw new TypeError("offline");
    return Response.json({ tempC: 25, humidityPct: 55, lightLux: 2,
      lightSource: "estimated", stale: false, sampledAt: "now" });
  }});
  await driver.readEnvironment();
  fail = true;
  expect(await driver.readEnvironment()).toMatchObject({ tempC: 25, stale: true });
});
```

- [ ] **Step 5: Verify GREEN and full TypeScript tests**

Run: `npx vitest run lib/hardware/rdk-x5.test.ts && npm test`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/hardware/driver.ts lib/hardware/rdk-x5.ts lib/hardware/rdk-x5.test.ts
git commit -m "feat: add RDK X5 hardware driver"
```

### Task 3: Driver Selection and Web Degradation

**Files:**
- Create: `lib/hardware/index.test.ts`
- Modify: `lib/hardware/index.ts`
- Modify: `app/api/env/route.ts`
- Modify: `components/DashboardClient.tsx`
- Modify: `components/SleepingClient.tsx`

**Interfaces:**
- Produces: `createDriver(env?: NodeJS.ProcessEnv): HardwareDriver`
- `GET /api/env` returns `{ env, health, light, targetTempC }`; on cold-start hardware failure, `env` is null and `health.ok` is false.

- [ ] **Step 1: Write failing factory tests**

```ts
it("selects RdkX5Driver only when explicitly configured", () => {
  expect(createDriver({ HARDWARE_DRIVER: "rdk-x5", RDK_X5_AGENT_URL: "http://rdk:8765" }))
    .toBeInstanceOf(RdkX5Driver);
  expect(createDriver({})).toBeInstanceOf(SimDriver);
});

it("requires an agent URL for real hardware", () => {
  expect(() => createDriver({ HARDWARE_DRIVER: "rdk-x5" }))
    .toThrow("RDK_X5_AGENT_URL");
});
```

- [ ] **Step 2: Verify RED**

Run: `npx vitest run lib/hardware/index.test.ts`
Expected: FAIL because `createDriver` is not exported.

- [ ] **Step 3: Implement factory and API degradation**

```ts
export function createDriver(env: NodeJS.ProcessEnv = process.env): HardwareDriver {
  if (env.HARDWARE_DRIVER !== "rdk-x5") return new SimDriver();
  if (!env.RDK_X5_AGENT_URL) throw new Error("RDK_X5_AGENT_URL is required");
  return new RdkX5Driver({ baseUrl: env.RDK_X5_AGENT_URL });
}
```

`/api/env` catches read failures, calls `health()`, and returns a stable JSON shape. Do not silently substitute simulated values while labeling the driver as real.

- [ ] **Step 4: Add UI hardware-state handling**

Dashboard stores `health` and `lightSource` from `/api/env`, shows compact text states `实机在线`、`硬件离线`、`光照为灯态估算`, and only renders the demo injection control when `health.driver === "sim"`. Sleeping view emits one notice after three failures and keeps retrying.

- [ ] **Step 5: Verify**

Run: `npx vitest run lib/hardware/index.test.ts && npm test && npx tsc --noEmit`
Expected: tests and typecheck PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/hardware/index.ts lib/hardware/index.test.ts app/api/env/route.ts components/DashboardClient.tsx components/SleepingClient.tsx
git commit -m "feat: expose real hardware health in web app"
```

### Task 4: Reproducible Board Deployment

**Files:**
- Create: `hardware/rdk-x5/baby-good-sleep-hardware.service`
- Create: `hardware/rdk-x5/install.sh`
- Create: `hardware/rdk-x5/README.md`
- Create: `.env.example`

**Interfaces:**
- Produces service: `baby-good-sleep-hardware.service`
- Listens: `0.0.0.0:8765`
- Installs binary: `/usr/local/bin/dht11-read`
- Installs agent: `/opt/baby-good-sleep/hardware_agent.py`

- [ ] **Step 1: Add service and installer**

```ini
[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/baby-good-sleep/hardware_agent.py --host 0.0.0.0 --port 8765
Restart=on-failure
RestartSec=2
```

The installer checks for `gcc`, Python 3, `libgpiod`, and importable `Hobot.GPIO`; compiles the C reader; installs files with explicit paths; reloads systemd; enables and restarts the service. It exits non-zero with a specific message when a prerequisite is missing.

- [ ] **Step 2: Add configuration example and operator docs**

```dotenv
DATABASE_URL="file:./dev.db"
HARDWARE_DRIVER=sim
RDK_X5_AGENT_URL=http://192.168.128.10:8765
STEPFUN_MODEL=step-3.5-flash
```

Document exact wiring, BatchMode SSH gate, installation command, curl health checks, LED safety stop, and rollback to `HARDWARE_DRIVER=sim`.

- [ ] **Step 3: Static verification**

Run: `bash -n hardware/rdk-x5/install.sh`
Run: `python3 -m py_compile hardware/rdk-x5/hardware_agent.py`
Expected: both commands exit 0.

- [ ] **Step 4: Commit**

```bash
git add hardware/rdk-x5/baby-good-sleep-hardware.service hardware/rdk-x5/install.sh hardware/rdk-x5/README.md .env.example
git commit -m "docs: add reproducible RDK X5 deployment"
```

### Task 5: Live Deployment and End-to-End Acceptance

**Files:**
- Modify locally only: `.env` (never stage or commit)
- No production code changes unless a failing test first reproduces a discovered bug.

- [ ] **Step 1: Verify non-interactive access**

Run: `ssh -o BatchMode=yes -o ConnectTimeout=5 rdkx5 'echo ok'`
Expected: exactly `ok`. If it fails, stop remote mutation and report the live blocker.

- [ ] **Step 2: Deploy the board service**

```bash
scp -r hardware/rdk-x5 rdkx5:/tmp/baby-good-sleep-rdk-x5
ssh rdkx5 'bash /tmp/baby-good-sleep-rdk-x5/install.sh /tmp/baby-good-sleep-rdk-x5'
```

- [ ] **Step 3: Verify the agent and sensors**

```bash
curl --fail http://192.168.128.10:8765/health
for i in $(seq 1 20); do curl --fail http://192.168.128.10:8765/environment; done
```

Expected: health `ok:true`; 20 valid JSON responses; failures after a valid read are marked stale.

- [ ] **Step 4: Verify each LED and safe off state**

POST warm/cool light requests at 5%, 10%, and 20%, visually confirm correct colors, then POST `{ "on": false, "brightness": 0, "colorTemp": "warm" }` and confirm all LEDs off.

- [ ] **Step 5: Enable the real driver locally**

Set local `.env` values `HARDWARE_DRIVER=rdk-x5` and `RDK_X5_AGENT_URL=http://192.168.128.10:8765`. The user supplies `STEPFUN_API_KEY` locally; never echo it.

- [ ] **Step 6: Full verification**

Run: `npm test`
Run: `npx tsc --noEmit`
Run: `npm run build`
Open the local app and verify: real DHT11 values appear; hardcoded “开夜灯/关灯” controls real LEDs within 3 seconds; StepFun natural language does the same when a key is configured; unplugging the board shows hardware offline without a blank page.

- [ ] **Step 7: Final status**

Report each acceptance result separately: local tests, build, SSH, agent health, DHT11, LED, hardcoded commands, StepFun, and offline degradation. Do not mark hardware or StepFun successful without live evidence.
