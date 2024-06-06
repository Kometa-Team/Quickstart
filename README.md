Pick your folder for the script you want to run from a powershell prompt

```
cd quickstart
python -m venv venv
.\venv\scripts\activate.ps1
python -m pip install --upgrade pip
pip install -r .\requirements.txt
```
Now you are ready to run it (with the venv activated)

`python app.py`

Or how to call it to run from the venv

`.\venv\scripts\python app.py`

Note: Ensure you have the necessary dependencies installed, particularly PIL.
