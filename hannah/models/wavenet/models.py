#
# Copyright (c) 2022 University of Tübingen.
#
# This file is part of hannah.
# See https://atreus.informatik.uni-tuebingen.de/ties/ai/hannah/hannah for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import math

import torch
import torch.nn as nn


class Conv(nn.Module):
    """
    A convolution with the option to be causal and use xavier initialization
    """

    def __init__(
        self,
        in_channels,
        out_channels,
        kernel_size=1,
        stride=1,
        dilation=1,
        bias=True,
        w_init_gain="linear",
        is_causal=False,
    ):
        super(Conv, self).__init__()
        self.is_causal = is_causal
        self.kernel_size = kernel_size
        self.dilation = dilation

        self.conv = torch.nn.Conv1d(
            in_channels,
            out_channels,
            kernel_size=kernel_size,
            stride=stride,
            dilation=dilation,
            bias=bias,
        )

        torch.nn.init.xavier_uniform(
            self.conv.weight, gain=torch.nn.init.calculate_gain(w_init_gain)
        )

    def forward(self, signal):
        if self.is_causal:
            padding = (int((self.kernel_size - 1) * (self.dilation)), 0)
            signal = torch.nn.functional.pad(signal, padding)
        return self.conv(signal)


class WaveNet(nn.Module):
    def __init__(self, config):
        super(WaveNet, self).__init__()
        self.non_causal_layers_per_layer = config["non_causal_layers_per_layer"]
        self.mu_quantization = config["mu_quantization"]
        self.n_classes = config["n_labels"]
        self.n_layers = config["n_layers"]
        self.max_dilation = config["max_dilation"]
        self.n_residual_channels = config["n_residual_channels"]
        self.n_in_channels = config["height"]
        self.n_out_channels = config["n_out_channels"]
        self.n_skip_channels = config["n_skip_channels"]
        self.input_length = config["width"]

        self.dilate_layers = torch.nn.ModuleList()
        self.res_layers = torch.nn.ModuleList()
        self.skip_layers = torch.nn.ModuleList()
        self.skip_layers_kw = torch.nn.ModuleList()
        self.non_causal_layers = torch.nn.ModuleList()

        self.conv_in = Conv(self.n_in_channels, self.n_residual_channels, 1)

        self.conv_out = Conv(
            self.n_skip_channels, self.n_out_channels, bias=False, w_init_gain="relu"
        )

        self.conv_out_kw = Conv(
            self.n_skip_channels, self.n_classes, bias=False, w_init_gain="relu"
        )

        self.conv_end = Conv(
            self.n_out_channels, self.n_out_channels, bias=False, w_init_gain="linear"
        )

        loop_factor = math.floor(math.log2(self.max_dilation)) + 1

        self.mean_pooling_layer = nn.AvgPool1d(kernel_size=self.input_length)

        for i in range(self.n_layers):
            dilation = 2 ** (i % loop_factor)

            # Kernel size is 2 in nv-wavenet
            in_layer = Conv(
                self.n_residual_channels,
                2 * self.n_residual_channels,
                kernel_size=2,
                dilation=dilation,
                w_init_gain="tanh",
                is_causal=True,
            )
            self.dilate_layers.append(in_layer)
            for j in range(self.non_causal_layers_per_layer):
                non_causal_layer = nn.Conv1d(
                    (2 * self.n_residual_channels // (2**j)),
                    (self.n_residual_channels // (2**j)),
                    kernel_size=2,
                )

                self.non_causal_layers.append(non_causal_layer)

            # last one is not necessary
            if i < self.n_layers - 1:
                res_layer = Conv(
                    self.n_residual_channels,
                    self.n_residual_channels,
                    w_init_gain="linear",
                )
                self.res_layers.append(res_layer)

            skip_layer = Conv(
                self.n_residual_channels, self.n_skip_channels, w_init_gain="relu"
            )

            self.skip_layers.append(skip_layer)

            skip_layer_kw = Conv(
                self.n_residual_channels
                // (2 ** (self.non_causal_layers_per_layer - 1)),
                self.n_skip_channels,
                w_init_gain="relu",
            )

            self.skip_layers_kw.append(skip_layer_kw)

            self.linear = nn.Linear(self.n_classes, self.n_classes)

    def forward(self, input_data):
        forward_input = self.conv_in(input_data)
        for i in range(self.n_layers):
            in_act = self.dilate_layers[i](forward_input)
            t_act = torch.tanh(in_act[:, : self.n_residual_channels, :])
            s_act = torch.sigmoid(in_act[:, self.n_residual_channels :, :])
            acts = t_act * s_act
            if i < len(self.res_layers):
                res_acts = self.res_layers[i](acts)
            forward_input = res_acts + forward_input

            if i == 0:
                output = self.skip_layers[i](acts)
            else:
                output = self.skip_layers[i](acts) + output

        output = self.conv_out_kw(output)
        output = self.mean_pooling_layer(output)
        output = output.view(output.size(0), -1)
        output = self.linear(output)

        return output
