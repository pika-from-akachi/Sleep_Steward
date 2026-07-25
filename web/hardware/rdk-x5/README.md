# RDK X5 硬件服务

该目录把 DHT11 和四颗 LED 封装为局域网 HTTP 服务。网站运行时调用 HTTP；SSH 只用于部署和诊断。

## 接线

所有 Pin 编号都是 RDK X5 40 Pin 排针的物理编号。

| 模块 | 物理 Pin | 用途 |
|---|---:|---|
| DHT11 | 1 | 3.3V |
| DHT11 | 9 | GND |
| DHT11 | 11 | DATA |
| 白色 LED | 13 | GPIO 输出 |
| 黄色 LED | 15 | GPIO 输出 |
| 蓝色 LED | 18 | GPIO 输出 |
| 红色 LED | 22 | GPIO 输出 |
| LED 公共地 | 20 | GND |

当前 LED 模块自带限流电阻。若以后换成裸 LED，必须为每颗 LED 串联合适的限流电阻，不能直接接 GPIO。

MAX30102 保持现有接线，不由本服务轮询：Pin 17 为 3.3V、Pin 14 为 GND、Pin 3 为 SDA、Pin 5 为 SCL。

## 部署

先确认板子开机并处于 `192.168.128.10` 所在网络：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 rdkx5 'echo ok'
```

只有输出 `ok` 才说明可自动部署。随后从项目根目录运行：

```bash
scp -r hardware/rdk-x5 rdkx5:/tmp/baby-good-sleep-rdk-x5
ssh rdkx5 'bash /tmp/baby-good-sleep-rdk-x5/install.sh /tmp/baby-good-sleep-rdk-x5'
```

安装脚本会编译 `/usr/local/bin/dht11-read`，安装 `/opt/baby-good-sleep/hardware_agent.py`，并启用 `baby-good-sleep-hardware.service`。

## 验证

```bash
ssh rdkx5 'systemctl status baby-good-sleep-hardware.service --no-pager'
curl --fail http://192.168.128.10:8765/health
curl --fail http://192.168.128.10:8765/environment
```

测试暖光 10%：

```bash
curl --fail -X POST http://192.168.128.10:8765/light \
  -H 'Content-Type: application/json' \
  -d '{"on":true,"brightness":10,"colorTemp":"warm"}'
```

测试完成后安全关灯：

```bash
curl --fail -X POST http://192.168.128.10:8765/light \
  -H 'Content-Type: application/json' \
  -d '{"on":false,"brightness":0,"colorTemp":"warm"}'
```

停止 systemd 服务时使用 `SIGINT`，代理会在退出前将四路 PWM 归零并释放 GPIO。

## 网站配置

在项目本地 `.env` 中配置：

```dotenv
HARDWARE_DRIVER=rdk-x5
RDK_X5_AGENT_URL=http://192.168.128.10:8765
```

StepFun Key 只写入本机 `.env` 的 `STEPFUN_API_KEY`，不要提交。修改环境变量后重启 Next.js 开发服务。

回退模拟器：

```dotenv
HARDWARE_DRIVER=sim
```

## 诊断

```bash
ssh rdkx5 'journalctl -u baby-good-sleep-hardware.service -n 100 --no-pager'
ssh rdkx5 '/usr/local/bin/dht11-read --json --attempts 12'
```

`environment` 返回 `stale: true` 表示本次 DHT11 读取失败，当前数值来自最后一次有效采样。`lightSource: "estimated"` 表示 lux 由灯光命令估算，并非光照传感器实测。
