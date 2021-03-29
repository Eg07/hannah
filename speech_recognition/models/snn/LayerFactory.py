from .SNNLayers import (
    SpikingDenseLayer,
    Spiking1DLayer,
    ReadoutLayer,
    SurrogateHeaviside,
    EmptyLayer,
    Surrogate_BP_Function,
)
import torch.nn as nn


def build1DConvolution(
    type,
    in_channels,
    out_channels,
    kernel_size=3,
    dilation=1,
    spike_fn=Surrogate_BP_Function.apply,
    stride=1,
    padding=0,
    w_init_mean=0.0,
    w_init_std=0.15,
    recurrent: bool = False,
    lateral_connections: bool = False,
    flatten_output: bool = False,
    groups: int = 1,
    bias: bool = True,
    padding_mode: str = "zeros",
    timesteps: int = 0,
    batchnorm="BN",
    activation=None,
):
    if type == "SNN":
        conv = nn.Conv1d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            groups=groups,
            bias=bias,
            padding_mode=padding_mode,
        )
        if batchnorm == "BNTT":
            return nn.Sequential(
                conv,
                Spiking1DLayer(
                    in_channels,
                    out_channels,
                    kernel_size,
                    dilation,
                    spike_fn,
                    stride=stride,
                    w_init_mean=w_init_mean,
                    w_init_std=w_init_std,
                    recurrent=recurrent,
                    lateral_connections=lateral_connections,
                    flatten_output=flatten_output,
                    convolution_layer=conv,
                    bntt=True,
                    timesteps=timesteps,
                ),
            )
        else:
            return nn.Sequential(
                conv,
                build1DBatchNorm(
                    out_channels=out_channels,
                    flatten_output=flatten_output,
                    timesteps=timesteps,
                ),
                Spiking1DLayer(
                    in_channels,
                    out_channels,
                    kernel_size,
                    dilation,
                    spike_fn,
                    stride=stride,
                    w_init_mean=w_init_mean,
                    w_init_std=w_init_std,
                    recurrent=recurrent,
                    lateral_connections=lateral_connections,
                    flatten_output=flatten_output,
                    convolution_layer=conv,
                    bntt=False,
                    timesteps=timesteps,
                ),
            )
    elif type == "NN" and activation != None:
        return nn.Sequential(
            nn.Conv1d(
                in_channels=in_channels,
                out_channels=out_channels,
                kernel_size=kernel_size,
                stride=stride,
                padding=padding,
                dilation=dilation,
                groups=groups,
                bias=bias,
                padding_mode=padding_mode,
            ),
            build1DBatchNorm(
                out_channels=out_channels,
                flatten_output=flatten_output,
                timesteps=timesteps,
            ),
            activation,
        )
    elif type == "NN" and activation == None:
        return nn.Sequential(
            nn.Conv1d(
                in_channels=in_channels,
                out_channels=out_channels,
                kernel_size=kernel_size,
                stride=stride,
                padding=padding,
                dilation=dilation,
                groups=groups,
                bias=bias,
                padding_mode=padding_mode,
            ),
            build1DBatchNorm(
                out_channels=out_channels,
                flatten_output=flatten_output,
                timesteps=timesteps,
            ),
        )

    else:
        print("Error wrong type Parameter")


def buildLinearLayer(
    type,
    input_shape,
    output_shape,
    w_init_mean=0.0,
    w_init_std=0.15,
    eps=1e-8,
    spike_fn=Surrogate_BP_Function.apply,
    time_reduction="mean",
    readout=False,
    recurrent=False,
    lateral_connections=False,
    bias=False,
):
    if type == "SNN" and readout:
        return ReadoutLayer(
            input_shape=input_shape,
            output_shape=output_shape,
            w_init_mean=w_init_mean,
            w_init_std=w_init_std,
            eps=eps,
            time_reduction=time_reduction,
        )

    elif type == "SNN" and not readout:
        return SpikingDenseLayer(
            input_shape=input_shape,
            output_shape=output_shape,
            spike_fn=spike_fn,
            w_init_mean=w_init_mean,
            w_init_std=w_init_std,
            eps=eps,
            recurrent=recurrent,
            lateral_connections=lateral_connections,
        )
    elif type == "NN":
        return nn.Linear(in_features=input_shape, out_features=output_shape, bias=bias)
    else:
        print("Error wrong type Parameter")


def build1DBatchNorm(out_channels, flatten_output: bool = False, timesteps: int = 0):
    return nn.BatchNorm1d(out_channels)


# else:
#    print("Error wrong type Parameter")
