import logging
import yaml


import pandas as pd

from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def prepare_summary(
    data: Dict[str, str], base_dir: str = ".", force: bool = False
) -> pd.DataFrame:
    """Prepare a summary of one or multiple nas runs

    Args:
        data (Dict[str, str]): A mapping from a short name for a nas run "e.g KWS" to a folder containing nas history file e.g. "trained_models/nas_kws/conv_net_trax"
        base_dir (str): base directory paths in data mapping are interpreted relative to base directory
        force (bool): force reconstructing of cached results ("data.pkl")
    """

    logger.info("Extracting design points")

    results_file = Path("data.pkl")
    base_dir = Path(base_dir)
    if results_file.exists() and not force:
        changed = False
        results_mtime = results_file.stat().st_mtime
        for name, source in data.items():
            history_path = base_dir / source / "history.yml"
            if history_path.exists():
                history_mtime = history_path.stat().st_mtime
                if history_mtime >= results_mtime:
                    changed = True
                    break
        if not changed:
            logger.info("  reading design points from saved data.pkl")
            return pd.read_pickle("data.pkl")

    result_stack = []
    for name, source in data.items():
        logger.info("  Extracting design points for task: %s", name)
        history_path = base_dir / source / "history.yml"
        with history_path.open("r") as f:
            history_file = yaml.unsafe_load(f)

        results = (h.result for h in history_file)
        metrics = pd.DataFrame(results)
        metrics["Task"] = name
        metrics["Step"] = metrics.index

        result_stack.append(metrics)

    result = pd.concat(result_stack)

    task_column = result.pop("Task")
    step_column = result.pop("Step")

    result.insert(0, "Step", step_column)
    result.insert(0, "Task", task_column)

    result.to_pickle(results_file)

    return result


def calculate_derived_metrics(
    result_metrics: pd.DataFrame, metric_definitions: Dict[str, Any]
):
    for name, metric_def in metric_definitions.items():
        derived = metric_def.get("derived", None)
        if derived is not None:
            try:
                result_metrics[name] = eval(derived, {}, {"data": result_metrics})
            except Exception as e:
                logger.critical("Could not calculate derived metric %s", name)
                logger.critical(str(e))

    return result_metrics
