import os
import logging
import shutil
import pathlib

import hydra
from omegaconf import DictConfig, OmegaConf
import torch
from torch.nn.modules import module

from pytorch_lightning.callbacks import LearningRateMonitor
from pytorch_lightning.trainer import Trainer
from pytorch_lightning.loggers import TensorBoardLogger, CSVLogger
from pytorch_lightning.callbacks import GPUStatsMonitor
from pytorch_lightning.utilities.seed import seed_everything
from hydra.utils import instantiate

from . import conf  # noqa
from .callbacks.summaries import MacSummaryCallback
from .callbacks.optimization import HydraOptCallback
from .callbacks.pruning import PruningAmountScheduler
from .utils import log_execution_env_state, auto_select_gpus


def handleDataset(config=DictConfig):
    lit_module = instantiate(
        config.module,
        dataset=config.dataset,
        model=config.model,
        optimizer=config.optimizer,
        features=config.features,
        scheduler=config.get("scheduler", None),
        normalizer=config.get("normalizer", None),
    )
    lit_module.prepare_data()


def train(config=DictConfig):
    test_output = []
    results = []
    if isinstance(config.seed, int):
        config.seed = [config.seed]

    for seed in config.seed:
        seed_everything(seed)
        if not torch.cuda.is_available():
            config.trainer.gpus = None

        if isinstance(config.trainer.gpus, int):
            config.trainer.gpus = auto_select_gpus(config.trainer.gpus)

        if not config.trainer.fast_dev_run:
            current_path = pathlib.Path(".")
            for component in current_path.iterdir():
                if component.name == "checkpoints":
                    shutil.rmtree(component)
                elif component.name.startswith("version_"):
                    shutil.rmtree(component)

        log_execution_env_state()

        logging.info("Configuration: ")
        logging.info(OmegaConf.to_yaml(config))
        logging.info("Current working directory %s", os.getcwd())

        checkpoint_callback = instantiate(config.checkpoint)
        lit_module = instantiate(
            config.module,
            dataset=config.dataset,
            model=config.model,
            optimizer=config.optimizer,
            features=config.features,
            scheduler=config.get("scheduler", None),
            normalizer=config.get("normalizer", None),
        )
        callbacks = []

        logger = [
            TensorBoardLogger(".", version=None, name="", default_hp_metric=False),
            CSVLogger(".", version=None, name=""),
        ]

        if config.get("backend", None):
            backend = instantiate(config.backend)
            callbacks.append(backend)

        logging.info("Starting training")

        profiler = None
        if config.get("profiler", None):
            profiler = instantiate(config.profiler)

        lr_monitor = LearningRateMonitor()
        callbacks.append(lr_monitor)

        if config.get("gpu_stats", None):
            gpu_stats = GPUStatsMonitor()
            callbacks.append(gpu_stats)

        mac_summary_callback = MacSummaryCallback()
        callbacks.append(mac_summary_callback)

        opt_monitor = config.get("monitor", ["val_error"])
        opt_callback = HydraOptCallback(monitor=opt_monitor)
        callbacks.append(opt_callback)

        if config.get("early_stopping", None):
            stop_callback = instantiate(config.early_stopping)
            callbacks.append(stop_callback)

        if config.get("pruning", None):
            pruning_scheduler = PruningAmountScheduler(
                config.pruning.amount, config.trainer.max_epochs
            )
            pruning_config = dict(config.pruning)
            del pruning_config["amount"]
            pruning_callback = instantiate(pruning_config, amount=pruning_scheduler)
            callbacks.append(pruning_callback)

        # INIT PYTORCH-LIGHTNING
        lit_trainer = Trainer(
            **config.trainer,
            profiler=profiler,
            callbacks=callbacks,
            checkpoint_callback=checkpoint_callback,
            logger=logger,
        )

        if config["auto_lr"]:
            # run lr finder (counts as one epoch)
            lr_finder = lit_trainer.lr_find(lit_module)

            # inspect results
            fig = lr_finder.plot()
            fig.savefig("./learning_rate.png")

            # recreate module with updated config
            suggested_lr = lr_finder.suggestion()
            config["lr"] = suggested_lr

        # PL TRAIN
        lit_trainer.fit(lit_module)
        ckpt_path = "best"

        if lit_trainer.fast_dev_run:
            logging.warning(
                "Trainer is in fast dev run mode, switching off loading of best model for test"
            )
            ckpt_path = None

        # PL TEST
        lit_trainer.test(ckpt_path=ckpt_path, verbose=False)
        if not lit_trainer.fast_dev_run:
            lit_module.save()
            if checkpoint_callback and checkpoint_callback.best_model_path:
                shutil.copy(checkpoint_callback.best_model_path, "best.ckpt")

        test_output.append(opt_callback.test_result())
        results.append(opt_callback.result())
    test_sum = {
        "test_accuracy": 0,
        "test_error": 0,
        "test_recall": 0,
        "test_precision": 0,
        "rest_f1": 0,
    }
    for output in test_output:
        for telement in [
            "test_accuracy",
            "test_error",
            "test_recall",
            "test_precision",
            "rest_f1",
        ]:
            test_sum[telement] += output[telement].item()

    logging.info("Averaged Test Metrics:")

    for telement in [
        "test_accuracy",
        "test_error",
        "test_recall",
        "test_precision",
        "rest_f1",
    ]:
        logging.info(telement + " : " + str(test_sum[telement] / len(test_output)))
    # TODO Change in diverse Backends as unas!
    if len(results) == 1:
        return results[0]
    else:
        return results


@hydra.main(config_name="config", config_path="conf")
def main(config: DictConfig):
    return train(config)


if __name__ == "__main__":
    main()
