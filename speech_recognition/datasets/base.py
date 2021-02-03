from abc import ABC, abstractmethod, abstractclassmethod, abstractproperty

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import torch

from torch.utils.data import Dataset


class DatasetType(Enum):
    """ The type of a dataset partition e.g. train, dev, test """

    TRAIN = 0
    DEV = 1
    TEST = 2


class AbstractDataset(Dataset, ABC):
    @abstractclassmethod
    def prepare(cls, config: Dict[str, Any]) -> None:
        """Prepare the dataset.

        This method is run at the beginning of the dataset training.

        If possible it should download the dataset from its original source, if
        it is available for public download.


        Args:
            config (Dict[Any]): The dataset configuration
        """

        pass

    @abstractclassmethod
    def splits(
        cls, config: Dict[str, Any]
    ) -> Tuple["AbstractDataset", "AbstractDataset", "AbstractDataset"]:
        """Returns the test, validation and train split according to the Dataset config

        Args:
            config ([type]): [description]
        """

        pass

    @abstractproperty
    def class_names(self) -> List[str]:
        """ Returns the names of the classes in the classification dataset """
        pass

    @abstractproperty
    def class_counts(self) -> Optional[Dict[int, int]]:
        """ Returns the number of items in each class of the dataset

        If this is not applicable to a dataset type e.g. ASR, Semantic Segementation,
        it may return None
        """
        pass

    @abstractmethod
    def __getitem__(self, index) -> List[torch.Tensor]:
        """Returns a torch.Tensor for the data item at the corresponding index

        The length of the list depends on the dataset item to use

        Args:
            index (int): the index of the data item
        """

        pass


def ctc_collate_fn(data):
    """Creates mini-batch tensors from the list of tuples (src_seq, trg_seq).
    We should build a custom collate_fn rather than using default collate_fn,
    because merging sequences (including padding) is not supported in default.
    Sequences are padded to the maximum length of mini-batch sequences (dynamic padding).
    Args:
        data: list of tuple (src_seq, src_length, trg_seq, trg_length).
            - src_seq: torch tensor of shape (x,?); variable length.
            - src length: torch tenso of shape 1x1
            - trg_seq: torch tensor of shape (?); variable length.
            - trg_length: torch_tensor of shape (1x1)
    Returns: tuple of four torch tensors
        src_seqs: torch tensor of shape (batch_size, x, padded_length).
        src_lengths: torch_tensor of shape (batch_size); valid length for each padded source sequence.
        trg_seqs: torch tensor of shape (batch_size, x, padded_length).
        trg_lengths: torch tensor of shape (batch_size); valid length for each padded target sequence.
    """

    def merge(sequences):
        lengths = [seq.shape[-1] for seq in sequences]
        max_length = max(lengths)

        padded_seqs = []

        for item in sequences:
            padded = torch.nn.functional.pad(
                input=item,
                pad=(0, max_length - item.shape[-1]),
                mode="constant",
                value=0,
            )
            padded_seqs.append(padded)

        return padded_seqs, lengths

    # seperate source and target sequences
    src_seqs, src_lengths, trg_seqs, trg_lengths = zip(*data)

    # merge sequences (from tuple of 1D tensor to 2D tensor)
    src_seqs, src_lengths = merge(src_seqs)
    trg_seqs, trg_lengths = merge(trg_seqs)

    return (
        torch.stack(src_seqs),
        torch.Tensor(src_lengths),
        torch.stack(trg_seqs),
        torch.Tensor(trg_lengths),
    )
