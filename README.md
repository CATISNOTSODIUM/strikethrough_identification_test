## Quick start
Install python libraries from `requirements.txt` or use `conda` to create your own virtual environment.
```bash
conda config --append channels pytorch
conda create --name <your_env_name> --file cyclegan_requirements.txt
conda activate <your_env_name>
```

To train the model, run `python3 src/train.py`.
To test the model, execute
```bash
python3 src/test.py -config tmp/[DEFAULT_LAST]/config.cfg -data test
```