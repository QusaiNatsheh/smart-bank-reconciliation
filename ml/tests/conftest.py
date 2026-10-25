from pathlib import Path

import pytest
from smart_reconcile_ml.generator import Generator, GeneratorConfig, save
from smart_reconcile_ml.train import train


@pytest.fixture(scope="session")
def small_dataset(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("data")
    config = GeneratorConfig(seed=1, partners_per_company=30, months=24)
    save(Generator(config).generate(), path, config)
    return path


@pytest.fixture(scope="session")
def trained_model(small_dataset, tmp_path_factory) -> Path:
    import os

    os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{tmp_path_factory.mktemp('mlflow')}/mlflow.db"
    out = tmp_path_factory.mktemp("model")
    train(small_dataset, out, rounds=300)
    return out
