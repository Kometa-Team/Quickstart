![image](./static/images/header.png)

![image](./static/images/wizard.webp)

Welcome to the Kometa Quickstart Wizard. Here are some steps to getting started.

After having cloned the repo and assuming you are on Windows and you have a folder on your machine called `pyprogs` where you cloned Quickstart, open a powershell prompt into the `pyprogs` folder and then:

```
cd Quickstart
python -m venv venv
.\venv\scripts\activate.ps1
python -m pip install --upgrade pip
pip install -r .\requirements.txt
pre-commit install
pre-commit autoupdate
```
Now you are ready to run it (with the venv activated)

`python app.py`

Or how to call it to run from the venv if you have closed the powershell prompt. Navigating to `pyprogs\Quickstart`

`.\venv\scripts\python app.py`

Which will look like this and then open up your favorite browswer and navigate to the listed URLs:
![image](./static/images/running-in-pwsh.png)

Note: Updates can then be performed pretty easily by opening up your Windows powershell prompt into the `pyprogs` directory and performing the following commands:
```
cd Quickstart
git checkout main
git stash
git stash clear
git pull
.\venv\scripts\activate.ps1
python -m pip install --upgrade pip
pip install -r .\requirements.txt
```

There is a `.envrc` in the project, so if you are using a linux-alike and install `direnv`, then just entering the project directory in your shell will do all the above for you and leave you ready to run `python app.py`.
