import logging

import torch.fx
from tvm.relay import op

from . import qat

try:
    import tvm.relay as relay
    import tvm
except ModuleNotFoundError:
    relay = None
    tvm = None


class QuantizationTracer(torch.fx.Tracer):

    LEAF_MODULES = [
        qat.Conv1d,
        qat.Conv2d,
        qat.ConvBn1d,
        qat.ConvBn2d,
        qat.ConvBnReLU1d,
        qat.ConvBnReLU2d,
        qat.ConvReLU1d,
        qat.ConvReLU2d,
    ]

    def is_leaf_module(self, module, module_qualified_name):
        for leaf_cls in self.LEAF_MODULES:
            if isinstance(module, leaf_cls):
                return True

        return super().is_leaf_module(module, module_qualified_name)

class RelayConverter(torch.fx.Interpreter):
    def __init__(self, graph_module):
        super().__init__(graph_module)

        if relay is None:
            raise Exception(
                "TVM does not seem to be installed, please make sure that 'import tvm.relay works'"
            )

        self.tvm_mod = None
        self.modules = {}
        for name, module in graph_module.named_modules():
            self.modules[name] = module

        self.outputs = {}
        self.func_args = []
        self.returns = []
        self.params = []

        self.module_map = {
            qat.Conv1d: self._handle_qat_conv,
            qat.Conv2d: self._handle_qat_conv,
            qat.ConvBn1d: self._handle_qat_conv,
            qat.ConvBn2d: self._handle_qat_conv,
            qat.ConvBnReLU1d: self._handle_qat_conv,
            qat.ConvBnReLU2d: self._handle_qat_conv,
        }

    def _handle_qat_conv(self, node, module, result):
        weight = module.weight
        bias = module.bias

        if hasattr(module, "bn"):
            weight, bias = torch.nn.utils.fuse_conv_bn_weights(
                module.weight,
                module.bias,
                module.bn.running_mean,
                module.bn.running_var,
                module.bn.eps,
                module.bn.weight,
                module.bn.bias,
            )

        padding = tuple(module.padding)
        stride = tuple(module.stride)
        dilation = tuple(module.dilation)
        groups = module.groups
        out_channels = module.out_channels

        quant_weight = module.weight_fake_quant.quantize(weight)
        quant_bias = module.bias_fake_quant.quantize(bias)

        weight = tvm.relay.Var(f"{node.name}.weight", tvm.relay.TensorType(quant_weight.shape, dtype=f'int{module.weight_fake_quant.bits}'))
        bias = tvm.relay.Var(f"{node.name}.bias", tvm.relay.TensorType(quant_bias.shape, dtype=f'int{module.bias_fake_quant.bits}'))

        inputs = list(node.all_input_nodes)
        data = self.outputs[inputs[0].name]

        if quant_weight.dim() == 3:
            conv_out = tvm.relay.nn.conv1d(data, 
                                           weight, 
                                           strides=stride, 
                                           padding=padding, 
                                           dilation=dilation, 
                                           groups=groups, 
                                           channels=out_channels,
                                           kernel_size=quant_weight.size(2),
                                           data_layout='NCW',
                                           kernel_layout='OIW',
                                           out_dtype='int32') #FIXME use proper out dtype
        elif quant_weight.dim() == 4:
            conv_out = tvm.relay.nn.conv2d(data,
                                           weight, 
                                           strides=stride,
                                           padding=padding,
                                           dilation=dilation,
                                           groups=groups,
                                           channels=out_channels,
                                           kernel_size=(quant_weight.size(2), quant_weight.size(3)),
                                           data_layout='NCHW',
                                           kernel_layout='OIHW',
                                           out_dtype='int32')
        else:
            raise Exception(f"Quantized weights of dimension {quant_weight.dim()} are not supported")

        if bias is not None:
            conv_out = tvm.relay.nn.bias_add(conv_out, bias)


        if isinstance(module, qat.ConvBnReLU1d) or isinstance(module, qat.ConvBnReLU2d):
            conv_out = tvm.relay.nn.relu(conv_out)

        conv_out = tvm.relay.right_shift(conv_out, tvm.relay.const(module.weight_fake_quant.bits, dtype='int32'))
        conv_out = tvm.relay.cast(conv_out, dtype=f'int{module.activation_post_process.bits}')
            
        self.outputs[node.name] = conv_out


    def _handle_module(self, node, result):
        module = self.modules[node.target]
        if type(module) in self.module_map:
            self.module_map[type(module)](node, module, result)
        else:
            raise Exception(f"Support for module: {module} is not supported")

    def _handle_placeholder(self, node, result):
        var = relay.var(node.name, relay.TensorType(result.shape))
        self.outputs[node.name] = var
        self.func_args.append(var)

    def _handle_output(self, node, result):
        inputs = list(node.all_input_nodes)
        
        for input in inputs:
            self.returns.append(self.outputs[input.name])

    def run_node(self, node):
        result = super().run_node(node)

        if node.op == "call_module":
            self._handle_module(node, result)
        elif node.op == "output":
            self._handle_output(node, result)
        elif node.op == "placeholder":
            self._handle_placeholder(node, result)
        else:
            raise Exception(f"Node {node} with op {node.op} is not supported")

        return result

    def propagate(self, *args):
        return super().run(*args)

    def run(self, input):
        tvm_mod = tvm.IRModule()

        super().run(input)

        ret = self.returns[0] if len(self.returns) == 1 else tvm.relay.Tuple(self.returns)
        free_vars = relay.analysis.free_vars(ret)

        function = relay.Function(free_vars, ret)
        tvm_mod["main"] = function

        print(tvm_mod)

        return tvm_mod, self.params 
