# GFLBans Web
## Ban Management system for GFL
#### GFLBans (C) Aurora 2021. Licensed Under GPLv3

Windows: Not Tested
macOS: Working
Linux: Working
FreeBSD: Working

## Development Instance

1) Download and install [MongoDB](https://www.mongodb.com/try/download/community)
2) Download and install [Python 3](https://www.python.org/downloads/)
3) Install pip and virtualenv support
  - On Linux you can use `sudo apt install python3-pip python3-virtualenv`
4) Clone the repository
5) Open a terminal in the repository directory
6) Create a virtualenv in the repo directory called `venv` using the `python3 -m venv venv` command.
7) Copy `.env.sample` to `.env` and change as required
8) Activate your virtual environment
9) Install dependencies using `pip install -r requirements.txt`
10) Start gflbans using `python3 -m gflbans.main` and goto http://localhost:3335 and confirm that GFLBans is running
11) Checkout a branch
  - Use `git checkout branchname` to check out the branch you want to work on
  - Use `git branch branchname` to create a branch (usually after having checked out `main`)
