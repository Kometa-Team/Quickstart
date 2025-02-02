# Quickstart

![Quickstart Logo](https://raw.githubusercontent.com/Kometa-Team/Quickstart/refs/heads/main/static/images/logo.webp)

Welcome to Kometa Quickstart! This Web UI tool will guide you through creating a Configuration File to use with Kometa.

Special Thanks to [bullmoose20](https://github.com/bullmoose20), [Chazlarson](https://github.com/chazlarson) and [Yozora](https://github.com/yozoraXCII) for the time spent developing this tool.

## Installing Quickstart

We recommend running Quickstart on a system as a Python script

These are high-level steps which assume the user has knowledge of python and pip, and the general ability to troubleshoot issues.

> **We strongly recommend running this yourself rather than relying on someone else to host Quickstart.**
>
> This ensures that connection attempts are made exclusively to services and machines accessible only to you. Additionally, all credentials are stored locally, safeguarding your sensitive information from being stored on someone else's machine.

1. Clone or download and unzip the repo.
```shell
git clone https://github.com/Kometa-Team/Quickstart
```

2. Move into the Quickstart directory.
```shell
cd Quickstart
```

3. Install dependencies (it is recommended to do this is a virtual environment):
```shell
pip install -r requirements.txt
```

4. If the above command fails, run the following command:
```shell
pip install -r requirements.txt --ignore-installed
```

At this point Quickstart has been installed, and you can verify installation by running:
```shell
python quickstart.py
```

You should see something similar to this:

![image](https://raw.githubusercontent.com/Kometa-Team/Quickstart/refs/heads/main/static/images/running-in-pwsh.png)

Navigate to one of the http addresses that you are presented with, and you should be taken to the Quickstart Welcome Page.

### Debugging & Changing Ports

Users can choose to enable debugging mode which will add verbose logging to the console window.

There are two ways to enable debugging:
- Add `--debug` to your Run Command, for example: `python quickstart.py --debug`
- Open the `.env` file at the root of the Quickstart directory, and set `QS_DEBUG=1`.

If you are already running Quickstart, you will need to re-start it from the console.

Quickstart will run on port 5000 by default, this can be amended in one of two ways:
- Add `--port=XXXX` to your Run Command, for example: `python quickstart.py --port=1234`
- Open the `.env` file at the root of the Quickstart directory, and set `QS_PORT=XXXX` where XXXX is the port you want to run on.

If you are already running Quickstart, you will need to re-start it from the console.
