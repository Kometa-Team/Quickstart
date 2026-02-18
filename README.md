<!--logo-start-->
![Quickstart Logo](static/images/logo.webp)
<!--logo-end-->
<!--shields-start-->
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/Kometa-Team/Quickstart?style=plastic)](https://github.com/Kometa-Team/Quickstart/releases)
[![Docker Image Version (latest semver)](https://img.shields.io/docker/v/kometateam/quickstart?label=docker&sort=semver&style=plastic)](https://hub.docker.com/r/kometateam/quickstart)
[![Docker Pulls](https://img.shields.io/docker/pulls/kometateam/quickstart?style=plastic)](https://hub.docker.com/r/kometateam/quickstart)
[![Develop GitHub commits since latest stable release (by SemVer)](https://img.shields.io/github/commits-since/Kometa-Team/Quickstart/latest/develop?label=Commits%20in%20Develop&style=plastic)](https://github.com/Kometa-Team/Quickstart/tree/develop)

[![Discord](https://img.shields.io/discord/822460010649878528?color=%2300bc8c&label=Discord&style=plastic)](https://discord.gg/NfH6mGFuAB)
[![Reddit](https://img.shields.io/reddit/subreddit-subscribers/Kometa?color=%2300bc8c&label=r%2FKometa&style=plastic)](https://www.reddit.com/r/Kometa/)
[![Wiki](https://img.shields.io/readthedocs/kometa?color=%2300bc8c&style=plastic)](https://kometa.wiki/en/latest/home/scripts/quickstart.html)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/meisnate12?color=%238a2be2&style=plastic)](https://github.com/sponsors/meisnate12)
[![Sponsor or Donate](https://img.shields.io/badge/-Sponsor%2FDonate-blueviolet?style=plastic)](https://github.com/sponsors/meisnate12)
<!--shields-end-->
<!--body1-start-->
## Welcome to Kometa Quickstart

## ✨ Features

Kometa Quickstart is more than just a YAML generator - it's a full interactive environment for configuring, validating, and running Kometa. Key features include:

![Quickstart Welcome Page](static/images/readme/quickstart-welcome.png)

### Multiple Ways to Run Quickstart
- **Local Python:** Works on Windows, macOS, and Linux
- **Frozen Builds:** Precompiled executables for Windows, macOS, and Linux (no Python required)
- **Docker Image:** Official image on Docker Hub with persistent `/config` volume support
- **Branch Support:** Choose between `master` (stable) and `develop` (bleeding-edge) branches for every runtime option

### Safe Playground Mode
- **Plex Test Libraries:** Downloadable from the start page so you can experiment without touching production libraries
- **No Risk to Production:** All Quickstart data, credentials, and configs are stored locally

### Config Management & History
- **SQLite-Backed Storage:** All configs and page data are stored in a database, so you can switch between configs at any time
- **Automatic Backups:** Every config is saved as a versioned `.yml` file for historical reference
- **Download & Run Anywhere:** Final configs can be downloaded and run outside Quickstart if preferred

### Guided, Validated Workflow
- **Step-by-Step Pages:** Each section validates its own data, giving you instant feedback before proceeding
- **Library Telemetry:** Pulls real Plex server data (Plex Pass status, library types, agent/scanner compatibility)
- **Dynamic Toggles & Templates:** Rich UI for enabling collections, overlays, and builder template variables
- **Filtered Page Search:** Find matches on Libraries and Settings pages and auto-expand matching sections
- **Settings Cog:** Quick access to runtime controls like debug mode and port changes from anywhere

![Libraries Page](static/images/readme/libraries-page.png)

### Built-in Kometa Runner
- **One-Click Execution:** The final page creates a Kometa virtual environment (if needed), installs dependencies, and runs `kometa.py` against the generated config
- **Run Command Builder:** Dynamically builds and previews CLI commands with flags like `--run`, `--operations-only`, `--times`, etc.
- **Process Management:** Start, stop, and monitor Kometa runs directly from the web interface

![Final Validation Runner](static/images/readme/final-validation-runner.png)

### Live Previews & Assets
- **Overlay Preview Generator:** Combines overlays and template variables into real-time preview images
- **Custom Artwork Uploads:** Drag-and-drop or fetch library images from a URL so you can see what the overlays look like on your favorite poster.

![Overlay Preview Canvas](static/images/readme/overlay-preview.png)

### Automatic Updates
- **Quickstart Self-Updater:** One-click update to latest master or develop branch
- **Kometa Sync:** Option to pull and update Kometa itself (nightly/master) before running

### Themes & Personalization
- **Theme Picker:** Switch between Kometa, Plex, Jellyfin, Emby, Seerr, and more with instant apply

### Analytics
- **Reingest & analytics:** Rebuild run history from `config/kometa/config/logs/*meta*.log*` plus archived logs in `config/cache/logscan/archive/`.
- **Stable run tracking:** Runs are deduped with a stable `run_key` and cached in `config/cache/logscan/ingest_cache.json`.
- **Missing people requests:** Deduped output is written to `config/cache/logscan/meta_people_missing.log` (metadata in `meta_people_missing.json`).
- **UI helpers:** Sortable table headers, config filter, analytics breakdowns, and per-run “Report” recommendations.

### Logscan Analyzer & Analytics Page
- **Logscan Analyzer:** Parses Kometa `meta.log` files to surface errors, run summaries, and missing items.
- **Analytics Page:** Interactive dashboard for run history, filters, and per-run recommendations.

![Analytics Page](static/images/readme/analytics-page.png)

### Import Existing Config
- **Import Config:** Launch import from the Welcome page to prefill settings, libraries, and templates.
- **YAML or ZIP:** Zip files must contain exactly one YAML config; `.ttf`/`.otf` fonts in the zip will be imported.
- **Preview required:** Quickstart always runs a preview before import and shows a line‑by‑line report (`imported / not imported`) with filters (All/Imported/Not Imported/Comments) and a downloadable report.
- **Plex credentials prompt:** If the import contains libraries, Plex validation is required for mapping. Quickstart will prompt for Plex URL/token if none are present; if the credentials in the file fail validation, you’ll be prompted to correct them and re‑run Preview.
- **Library mapping:** Imported library names must be mapped to Plex libraries (or ignored) before confirming the import; you can re‑preview after mapping.
- **After import:** Quickstart redirects to Final Validation. Review each page and validate services (Plex/TMDB/etc.) before generating the final config.

![Import Config](static/images/readme/import-config.png)

### Quickstart Scope
- **Quickstart support vs Kometa support:** The Support Info workflow is for Quickstart issues. Kometa runtime issues should be handled in Kometa support channels.

### Support & Troubleshooting
- **Support Info (every page):** Use the Support Info button to gather system info and the Quickstart log tail.
- **Redaction notice:** We attempt to redact secrets, but always review before posting.
- **Log file:** `config/logs/quickstart.log`

### Data & Privacy (Quickstart)
- **Local-first:** Config data is stored locally in SQLite and versioned `.yml` files in `config/`.
- **Network access:** Quickstart only contacts external services when you validate settings or fetch remote assets.

Kometa Quickstart is a guided Web UI that helps you create a Configuration File for use with Kometa.

Special thanks to [meisnate12](https://github.com/meisnate12), [bullmoose20](https://github.com/bullmoose20), [chazlarson](https://github.com/chazlarson), and [Yozora](https://github.com/yozoraXCII) for their contributions to this tool.

## Table of Contents

- [Welcome to Kometa Quickstart](#welcome-to-kometa-quickstart)
- [✨ Features](#-features)
  - [Multiple Ways to Run Quickstart](#multiple-ways-to-run-quickstart)
  - [Safe Playground Mode](#safe-playground-mode)
  - [Config Management \& History](#config-management--history)
  - [Guided, Validated Workflow](#guided-validated-workflow)
  - [Built-in Kometa Runner](#built-in-kometa-runner)
  - [Live Previews \& Assets](#live-previews--assets)
  - [Automatic Updates](#automatic-updates)
  - [Themes \& Personalization](#themes--personalization)
  - [Analytics](#analytics)
  - [Logscan Analyzer \& Analytics Page](#logscan-analyzer--analytics-page)
  - [Import Existing Config](#import-existing-config)
  - [Quickstart Scope](#quickstart-scope)
  - [Support \& Troubleshooting](#support--troubleshooting)
  - [Data \& Privacy (Quickstart)](#data--privacy-quickstart)
- [Table of Contents](#table-of-contents)
- [Prerequisites](#prerequisites)
- [Installing Quickstart](#installing-quickstart)
- [1 - Installing on Windows](#1---installing-on-windows)
- [2 - Installing on Mac](#2---installing-on-mac)
- [3 - Installing on Ubuntu (Linux)](#3---installing-on-ubuntu-linux)
- [4 - Running in Docker](#4---running-in-docker)
  - [`docker run`](#docker-run)
  - [`docker compose`](#docker-compose)
- [5 - Installing locally](#5---installing-locally)
  - [Windows:](#windows)
  - [Linux/Mac:](#linuxmac)
  - [Debugging \& Changing Ports](#debugging--changing-ports)

## Prerequisites

We recommend completing the Kometa installation walkthrough before running Quickstart. This prepares Kometa to accept the configuration file Quickstart generates. Running Quickstart first may lead to mismatches with the walkthrough and issues that the walkthrough does not address.

Completing the walkthrough will also familiarize you with creating a Python virtual environment, which is recommended when running this as a Python script.

## Installing Quickstart

There are five primary ways to install and run Quickstart, listed from simplest to more advanced.
<!--body1-end-->
> [!CAUTION]
> **We strongly recommend running this yourself rather than relying on someone else to host Quickstart.**
>
> This ensures that connection attempts are made exclusively to services and machines accessible only to you. Additionally, all credentials are stored locally, safeguarding your sensitive information from being stored on someone else's machine.

<!--body2-start-->
## 1 - Installing on Windows

- Go to the [Releases page](https://github.com/Kometa-Team/Quickstart/releases) and download the standalone `.exe`.

- Choose the build you want (`master` or `develop`) and download the appropriate asset.

- Place the file in its own folder and double-click to run it.

- Manage Quickstart from the system tray icon.

![image](static/images/readme/system-tray-launcher.png)

## 2 - Installing on Mac

- Go to the [Releases page](https://github.com/Kometa-Team/Quickstart/releases) and download the standalone file.

- Choose the build you want (`master` or `develop`) and download the appropriate asset.

- Place the file in its own folder.

- Open Terminal, navigate to the folder, and make the file executable: `chmod 755 <name of file>`.

- Run it: `./<name of file>`.

- You may need to allow unsigned applications in macOS System Settings under Privacy & Security.

![image](static/images/readme/macos-settings-privacy-and-security.png)

-  Manage Quickstart from the system tray icon.

![image](static/images/readme/system-tray-launcher-mac.png)

## 3 - Installing on Ubuntu (Linux)

- Go to the [Releases page](https://github.com/Kometa-Team/Quickstart/releases) and download the standalone file.

- Choose the build you want (`master` or `develop`) and download the appropriate asset.

- Place the file in its own folder.

- Open a terminal, navigate to the folder, and make the file executable: `chmod 755 <name of file>`.

- Run it: `./<name of file>`.

- Manage Quickstart from the system tray icon.

![image](static/images/readme/system-tray-launcher-ubuntu.png)

<!--body2-end-->
> [!WARNING]
> You will likely need to perform these steps first to have a system tray icon show up:

Ubuntu/Debian:
```
sudo apt update
sudo apt install -y libxcb-xinerama0 libxcb-xinerama0-dev libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0
```
Fedora 42+:

On GNOME (especially on Wayland), classic system tray icons are not shown by default. Apps using Qt/PyQt “system tray” often appear to be “missing” even though they’re running fine.

The most common fix (GNOME): install AppIndicator support

On Fedora, install the GNOME extension that restores tray/appindicator icons:

```
sudo dnf install gnome-shell-extension-appindicator
```

Then enable it:
![image](static/images/readme/extension-manager.png)

Open Extensions app (or “Extension Manager” if you use it)

Enable AppIndicator and KStatusNotifierItem Support (After a new installation, you might need to reboot before you see both)

After that, the tray icon usually appears.

![image](static/images/readme/system-tray-launcher-fedora.png)

<!--body3-start-->
## 4 - Running in Docker

NOTE: The `/config` directory in these examples is NOT the Kometa config directory. Create a Quickstart-specific directory and map it to `/config`.

Here are some minimal examples:

### `docker run`

```
docker run -it -v "/path/to/config:/config:rw" kometateam/quickstart:develop
```

### `docker compose`

```yaml
services:
  quickstart:
    image: kometateam/quickstart:develop
    container_name: quickstart
    ports:
      - 7171:7171
    environment:
      - TZ=TIMEZONE #optional
    volumes:
      - /path/to/config:/config #edit this line for your setup
    restart: unless-stopped
```

## 5 - Installing locally

### Windows:


1.  Ensure Git and Python are installed.

Git: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git

Python: https://www.python.org/downloads/windows/

2.  `git clone` Quickstart, switch to your preferred branch (`develop`, `master`), create and activate a virtual environment, upgrade pip, and install the requirements.

Run the following commands within your Command Prompt window:

```
cd c:\this\dir\has
git clone https://github.com/Kometa-Team/Quickstart
cd Quickstart
git checkout develop
git stash
git stash clear
git pull
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4.  Run Quickstart. After completing the guided pages, the final page will automatically create the Kometa virtual environment, install the requirements, and allow you to run `kometa.py` using the validated config generated by Quickstart.

```
python quickstart.py
```

### Linux/Mac:


1.  Ensure Git and Python are installed.

Git: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git

Python:

Mac: https://www.python.org/downloads/macos/

Ubuntu/Debian: ```sudo apt-get install python3```

Fedora: ```sudo dnf install python3```

2.  `git clone` Quickstart, switch to your preferred branch (`develop`, `master`), create and activate a virtual environment, upgrade pip, and install the requirements.

```
cd /this/dir/has
git clone https://github.com/Kometa-Team/Quickstart
cd Quickstart
git checkout develop
git stash
git stash clear
git pull
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

4.  Run Quickstart. After completing the guided pages, the final page will automatically create the Kometa virtual environment, install the requirements, and allow you to run `kometa.py` using the validated config generated by Quickstart.

```
source venv/bin/activate
python3 quickstart.py
```

At this point, Quickstart has been installed and you should see something similar to this:

![image](static/images/readme/running-in-pwsh.png)

Quickstart should launch a browser automatically. If you are on a headless machine (Docker or Linux without a GUI), open a browser and navigate to the IP address of the machine running Quickstart; you should be taken to the Quickstart Welcome Page.

- Manage Quickstart from the system tray icon

![image](static/images/readme/system-tray-launcher.png)

### Debugging & Changing Ports

You can enable debug mode to add verbose logging to the console window.

There are three ways to enable debugging:

- Add `--debug` to your Run Command, for example: `python quickstart.py --debug`.

- Open the `.env` file at the root of the Quickstart directory, and set `QS_DEBUG=1` (restart required).

- Use the Quickstart system tray icon to toggle it on or off (no restart required).
- Use the Settings cog in the UI to toggle it on or off (no restart required).

Quickstart runs on port 7171 by default. You can change it in one of three ways:

- Add `--port=XXXX` to your Run Command, for example: `python quickstart.py --port=1234`

- Open the `.env` file at the root of the Quickstart directory, and set `QS_PORT=XXXX` where XXXX is the port you want to run on. (restart required)

- Use the Quickstart system tray icon to choose a new port (restarts automatically).
- Use the Settings cog in the UI to choose a new port (restarts automatically).

<!--body3-end-->
