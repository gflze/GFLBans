# GFLBans Web
## Ban Management system for GFL
#### GFLBans (C) Aurora 2021. Licensed Under GPLv3

Windows: Not Tested
macOS: Working
Linux: Working
FreeBSD: Working

## Setup

1) Download and install [Python 3](https://www.python.org/downloads/), pip, virtualenv support, and [Redis](https://redis.io/downloads/)
  - On Linux you can use `sudo apt install python3 python3-pip python3-virtualenv redis-server`
2) Download and install [MongoDB](https://www.mongodb.com/try/download/community)
3) Clone the repository
4) Open a terminal in the repository directory
5) Create a virtualenv in the repo directory called `venv` using the `python3 -m venv venv` command.
6) Copy `.env.sample` to `.env` and change as required
7) Activate your virtual environment using `source venv/bin/activate`
8) Install dependencies using `pip install -r requirements.txt`
9) Start gflbans using `python3 -m gflbans.main` and goto http://localhost:3335 and confirm that GFLBans is running

### Optional (for production)
10) Duplicate all html files in `templates/configs` with `.example` removed and configure as desired.
11) Reverse proxy GFLBans behind a webserver e.g. nginx
12) Create a systemctl service for GFLBans, to ensure it always runs

## Gameserver Plugins

- [Counter-Strike 2](https://github.com/Frozen-H2O/CS2_Fixes/tree/gflbans) - Requires [Metamod](https://www.sourcemm.net/downloads.php/?branch=master)
- [Source 1](https://github.com/GFLClan/sm_gflbans) - Requires [Metamod](https://www.sourcemm.net/downloads.php/?branch=master) and [Sourcemod](https://www.sourcemod.net/downloads.php)
