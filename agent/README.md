# Benergy GPU Agent

Real-time GPU monitoring agent for AI teams. Tracks GPU utilization, memory usage, and compute costs.

## Quick Start (2 min)

### 1. Install

```bash
pip install benergy-agent
```

### 2. Setup

```bash
benergy-agent
```

This will:

- ✅ Check for NVIDIA GPU
- ✅ Ask for your API key
- ✅ Create config file
- ✅ Start monitoring

### 3. View Dashboard

```
https://benergy.onrender.com/dashboard
```

That’s it! Your GPU metrics will start appearing in ~1 minute.

-----

## What It Does

The agent:

- 📊 Runs on your GPU machine
- 📡 Collects GPU metrics every 60 seconds
- 🔐 Sends to Benergy API (encrypted)
- 📝 Logs to `~/.benergy/agent.log`
- 🎯 Shows you real savings opportunities

-----

## Requirements

- **GPU:** NVIDIA GPU with CUDA support
- **OS:** Linux (Mac/Windows coming soon)
- **Python:** 3.8+
- **Tools:** `nvidia-smi` (included with NVIDIA drivers)

### Check if you have nvidia-smi:

```bash
nvidia-smi
```

Should show your GPU info. If not, install NVIDIA drivers first.

-----

## Installation

### Option 1: Pip (Easiest)

```bash
pip install benergy-agent
benergy-agent
```

### Option 2: From GitHub

```bash
git clone https://github.com/Benergy-io/Benergy.git
cd Benergy/agent
pip install -e .
benergy-agent
```

### Option 3: Docker (Coming soon)

```bash
docker pull benergy/agent:latest
docker run -e API_KEY=xyz benergy/agent
```

-----

## Configuration

### First Run

```bash
benergy-agent
```

This launches the setup wizard:

1. ✅ Detects GPU
1. 📝 Asks for API key
1. 💾 Saves config to `~/.benergy/config.json`
1. 🚀 Starts monitoring

### Get Your API Key

1. Go to https://benergy.onrender.com
1. Sign up (free)
1. Copy your API key
1. Paste in the agent setup

### Manual Config

Edit `~/.benergy/config.json`:

```json
{
  "api_key": "your-api-key-here",
  "created_at": "2026-06-08T12:00:00"
}
```

-----

## Running the Agent

### Foreground (Testing)

```bash
benergy-agent
```

Ctrl+C to stop.

### Background (Production)

#### Linux (systemd)

```bash
# Create service file
sudo tee /etc/systemd/system/benergy-agent.service > /dev/null << EOF
[Unit]
Description=Benergy GPU Agent
After=network.target

[Service]
Type=simple
User=$USER
ExecStart=$(which benergy-agent)
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable benergy-agent
sudo systemctl start benergy-agent

# Check status
sudo systemctl status benergy-agent

# View logs
sudo journalctl -u benergy-agent -f
```

#### Linux (tmux)

```bash
tmux new-session -d -s benergy "benergy-agent"
```

#### Linux (nohup)

```bash
nohup benergy-agent > ~/.benergy/agent.log 2>&1 &
```

-----

## Logs

All logs go to: `~/.benergy/agent.log`

View logs:

```bash
tail -f ~/.benergy/agent.log
```

Example log output:

```
2026-06-08 12:00:00 - INFO - 🚀 Benergy GPU Agent Started
2026-06-08 12:00:00 - INFO - 📍 API: https://benergy.onrender.com
2026-06-08 12:00:00 - INFO - ⏱️  Interval: 60s
2026-06-08 12:01:00 - INFO - ✅ Metrics sent: util=45%, mem=4096MB, temp=58°C
2026-06-08 12:02:00 - INFO - ✅ Metrics sent: util=42%, mem=4000MB, temp=57°C
```

-----

## Troubleshooting

### “No NVIDIA GPU detected”

```bash
# Check for nvidia-smi
which nvidia-smi

# If not found, install NVIDIA drivers:
# Ubuntu: sudo apt-get install nvidia-utils
# CentOS: sudo yum install nvidia-utils
```

### “Failed to connect to API”

```bash
# Check internet connection
ping benergy.onrender.com

# Check firewall
sudo ufw status

# Check API is up
curl https://benergy.onrender.com/health
```

### “Invalid API key”

```bash
# Get new API key from dashboard
# Edit config
nano ~/.benergy/config.json

# Restart agent
```

### “Agent keeps stopping”

```bash
# Check logs
tail -f ~/.benergy/agent.log

# Increase verbosity (future version)
# For now, check GPU drivers
nvidia-smi
```

-----

## Privacy & Security

- 🔐 **API key is encrypted** in config file (chmod 600)
- 📡 **Data sent via HTTPS** (TLS 1.2+)
- 🚫 **We only track GPU metrics**, nothing else
- 📝 **No personal data collected**
- ✅ **Open source** - audit the code

-----

## Support

- 📧 Email: hello@benergy.io
- 🐛 Issues: https://github.com/Benergy-io/Benergy/issues
- 💬 Twitter: @benergy_io

-----

## License

MIT - See LICENSE file

-----

## Changelog

### v0.1.0 (June 2026)

- ✅ Initial release
- ✅ GPU metric collection
- ✅ API integration
- ✅ Setup wizard
