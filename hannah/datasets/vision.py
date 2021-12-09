import os

from hydra.utils import get_original_cwd
import numpy as np
import torchvision
import torchvision.datasets as datasets
import torch.utils.data as data
import albumentations as A
from albumentations.pytorch.transforms import ToTensorV2

from .base import AbstractDataset


class VisionDatasetBase(AbstractDataset):
    """Wrapper around torchvision classification datasets"""

    def __init__(self, config, dataset, transform=None):
        self.config = config
        self.dataset = dataset
        self.transform = transform

    @property
    def class_counts(self):
        return None

    def __getitem__(self, index):
        data, target = self.dataset[index]
        data = np.array(data)
        if self.transform:
            data = self.transform(image=data)["image"]
        return data, target

    def size(self):
        dim = self[0][0].size()

        return list(dim)

    def __len__(self):
        return len(self.dataset)


class Cifar10Dataset(VisionDatasetBase):
    @classmethod
    def prepare(cls, config):
        data_folder = config.data_folder
        root_folder = os.path.join(data_folder, "CIFAR10")
        _ = datasets.CIFAR10(root_folder, train=False, download=True)

    @property
    def class_names(self):
        classes = [
            "airplane",
            "automobile",
            "bird",
            "cat",
            "deer",
            "dog",
            "frog",
            "horse",
            "ship",
            "truck",
        ]
        return classes

    @classmethod
    def splits(cls, config):
        data_folder = config.data_folder
        root_folder = os.path.join(data_folder, "CIFAR10")

        #train_transform = A.load(
        #    "/local/gerum/speech_recognition/albumentations/cifar10_autoalbument.json"
        #)
        # print(loaded_transform)
        train_transform = A.Compose(
            [
                A.SmallestMaxSize(max_size=32),
                A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.05, rotate_limit=15, p=0.5),
                A.RandomCrop(height=32, width=32),
                A.RGBShift(r_shift_limit=15, g_shift_limit=15, b_shift_limit=15, p=0.5),
                A.RandomBrightnessContrast(p=0.5),
                A.Normalize(mean=(0.4914, 0.4822, 0.4465), std=(0.247, 0.243, 0.261)),
                ToTensorV2(),
            ]
        )

        val_transform = A.Compose(
            [
                A.SmallestMaxSize(max_size=32),
                A.Normalize(mean=(0.4914, 0.4822, 0.4465), std=(0.247, 0.243, 0.261)),
                ToTensorV2(),
            ]
        )

        test_set = datasets.CIFAR10(root_folder, train=False, download=False)
        train_val_set = datasets.CIFAR10(root_folder, train=True, download=False)
        train_val_len = len(train_val_set)

        split_sizes = [int(train_val_len * 0.9), int(train_val_len * 0.1)]
        train_set, val_set = data.random_split(train_val_set, split_sizes)

        return (
            cls(config, train_set, train_transform),
            cls(config, val_set, val_transform),
            cls(config, test_set, val_transform),
        )


class FakeDataset(VisionDatasetBase):
    @classmethod
    def prepare(cls, config):
        pass

    @classmethod
    def splits(cls, config):
        transform = torchvision.transforms.Compose([torchvision.transforms.ToTensor()])

        test_data = torchvision.datasets.FakeData(
            size=128,
            image_size=(3, 32, 32),
            num_classes=config.num_classes,
            transform=transform,
        )
        val_data = torchvision.datasets.FakeData(
            size=128,
            image_size=(3, 32, 32),
            num_classes=config.num_classes,
            transform=transform,
        )
        train_data = torchvision.datasets.FakeData(
            size=512,
            image_size=(3, 32, 32),
            num_classes=config.num_classes,
            transform=transform,
        )

        return cls(config, train_data), cls(config, val_data), cls(config, test_data)

    @property
    def class_names(self):
        return [f"class{n}" for n in range(self.config.num_classes)]


class KvasirCapsuleDataset(VisionDatasetBase):
    DOWNLOAD_URL = "https://files.osf.io/v1/resources/dv2ag/providers/googledrive/?zip="

    @classmethod
    def prepare(cls, config):
        download_and_extract_archive(cls.DOWNLOAD_URL)

    def splits():
        pass
