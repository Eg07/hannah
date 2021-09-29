import copy
import logging
import torch
import torch.nn as nn
import torch.nn.functional as nnf
from ..utilities import filter_primary_module_weights, filter_single_dimensional_weights


class ElasticWidthBatchnorm1d(nn.BatchNorm1d):
    def __init__(
        self,
        num_features,
        track_running_stats=False,
    ):
        super().__init__(
            num_features=num_features,
            track_running_stats=track_running_stats
        )
        self.channel_filter = [True] * num_features

    def forward(self, input: torch.Tensor) -> torch.Tensor:

        if self.track_running_stats:
            logging.warn("ElasticWidthBatchnorm with tracked running stats currently not fully implemented!")
            # num_batches_tracked and exponential averaging are currently not implemented.

        running_mean = self.running_mean
        running_var = self.running_var
        weight = self.weight
        bias = self.bias
        training = self.training
        momentum = self.momentum
        eps = self.eps

        if all(self.channel_filter):
            # if the channels are unfiltered, the full batchnorm can be used
            return nnf.batch_norm(
                input=input,
                running_mean=running_mean,
                running_var=running_var,
                weight=weight,
                bias=bias,
                training=training or not self.track_running_stats,
                momentum=momentum,
                eps=eps
            )

        else:
            new_running_mean = None
            new_running_var = None
            if self.track_running_stats:
                new_running_mean = filter_single_dimensional_weights(running_mean, self.channel_filter)
                new_running_var = filter_single_dimensional_weights(running_var, self.channel_filter)
            new_weight = filter_single_dimensional_weights(weight, self.channel_filter)
            new_bias = filter_single_dimensional_weights(bias, self.channel_filter)

            return nnf.batch_norm(
                input=input,
                running_mean=new_running_mean,
                running_var=new_running_var,
                weight=new_weight,
                bias=new_bias,
                training=training or not self.track_running_stats,
                momentum=momentum,
                eps=eps
            )

    def get_basic_batchnorm1d(self):
        # filter_single_dimensional_weights checks for None-input, no need to do it here.
        new_running_mean = filter_single_dimensional_weights(self.running_mean, self.channel_filter)
        new_running_var = filter_single_dimensional_weights(self.running_var, self.channel_filter)
        new_weight = filter_single_dimensional_weights(self.weight, self.channel_filter)
        new_bias = filter_single_dimensional_weights(self.bias, self.channel_filter)
        new_bn = nn.BatchNorm1d(
            num_features=self.num_features,
            eps=self.eps,
            momentum=self.momentum,
            affine=self.affine,
            track_running_stats=self.track_running_stats
        )
        new_bn.running_mean = new_running_mean
        new_bn.running_var = new_running_var
        new_bn.weight = new_weight
        new_bn.bias = new_bias
        return new_bn

    def assemble_basic_batchnorm1d(self) -> nn.BatchNorm1d:
        return copy.deepcopy(self.get_basic_batchnorm1d())


class ElasticWidthLinear(nn.Linear):
    def __init__(self, in_features: int, out_features: int, bias: bool = True) -> None:
        super().__init__(in_features, out_features, bias=bias)
        self.in_channel_filter = [True] * self.in_features
        self.out_channel_filter = [True] * self.out_features

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        if all(self.in_channel_filter) and all(self.out_channel_filter):
            # if no channel filtering is required, simply use the full linear
            return nnf.linear(input, self.weight, self.bias)
        else:
            # if channels need to be filtered, apply filters.
            new_weight = filter_primary_module_weights(self.weight, self.in_channel_filter, self.out_channel_filter)
            # if the module has a bias parameter, also apply the output filtering to it.
            # filter_single_dimensional_weights checks for None-input, so no check is done here.
            new_bias = filter_single_dimensional_weights(self.bias, self.out_channel_filter)
            return nnf.linear(input, new_weight, new_bias)

    def get_basic_linear(self):
        weight = self.weight
        bias = self.bias
        # weight and bias of this linear will be overwritten
        new_linear = nn.Linear(
            in_features=self.in_features,
            out_features=self.out_features,
        )
        if all(self.in_channel_filter) and all(self.out_channel_filter):
            new_linear.weight = weight
            new_linear.bias = bias
            return new_linear
        else:
            new_weight = filter_primary_module_weights(self.weight, self.in_channel_filter, self.out_channel_filter)
            new_bias = filter_single_dimensional_weights(self.bias, self.out_channel_filter)
            new_linear.weight = new_weight
            new_linear.bias = new_bias
            return new_linear

    def assemble_basic_linear(self):
        return copy.deepcopy(self.get_basic_linear())
