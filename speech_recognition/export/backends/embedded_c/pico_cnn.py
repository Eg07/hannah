from .ir import *
from .utils import reduce_mult

from jinja2 import Environment, FileSystemLoader

import numpy as np

import os

base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "code_templates")

template_env = Environment(loader=FileSystemLoader(template_dir))

class BaseLayer(object):
    def __init__(self, node, graph):
        print("Generating layer", node.name)
        self.node = node
        self.graph = graph
        self.attributes = {}
    

    def generate_code(self):
        template = template_env.get_template(self.template_file)
        return template.render(**self.attributes)


    @classmethod
    def create(cls, node, graph, memory_manager):
        pass

    
class Conv1D(BaseLayer):
    name = "PicoCNNConv1D"
    operator = "Conv"
    template_file = "pico_cnn_conv1d.c"    

    @classmethod
    def create(cls, node, graph, memory_manager):
        operation = cls(node, graph)

        attrs = node.attrs        
        input_buffers = [memory_manager.get_buffer(graph, id) for id in node.inputs]
        output_buffers = [memory_manager.get_buffer(graph, id) for id in node.outputs]

        
        input_shape = input_buffers[0].shape

        if not (len(input_shape) == 3 or (len(input_shape) == 4 and input_shape[3] == 1)):
            print("{} is not a 1DConvolution".format(node.name))
            return None
        
        input_size = input_shape[2]
        input_channels = input_shape[1]
        
        output_shape = output_buffers[0].shape
        output_channels = output_shape[1]
        output_size = output_shape[2]

        
        size = attrs["kernel_shape"][0]
        stride = attrs["strides"][0]
        dilation = attrs["dilations"][0]

        #TODO: handle auto padding
        if "auto_pad" in attrs:
            print("{} auto padding is currently not supported".format(node.name))
            return None
        
        pads = (attrs["pads"][0], attrs["pads"][1]) if len(attrs["pads"]) == 2 else (attrs["pads"][0], attrs["pads"][2]) 
        
        if pads[0] != pads[1]:
            print("PicoCNN only supports same padding in all directions")
            return None
        
        padding = pads[0]

        operation.attributes['size'] = size
        operation.attributes['stride'] = stride
        operation.attributes['padding'] = padding
        operation.attributes['input_channels'] = input_channels
        operation.attributes['input_size'] = input_size
        operation.attributes['output_channels'] = output_channels
        operation.attributes['padding'] = padding
        operation.attributes['input_buffer'] = input_buffers[0]
        operation.attributes['weight_buffer'] = input_buffers[1]
        operation.attributes['output_feature_size'] = output_buffers[0].shape[2]
        if len(input_buffers) > 2:
               operation.attributes['bias_buffer'] = input_buffers[2]

        operation.attributes['output_buffer'] = output_buffers[0]
        operation.attributes['dilation'] = dilation
               
        return  operation

OperationRegistry.register(Conv1D)
            
class FullyConnected(BaseLayer):
    name = "PicoCNNFullyConnected"
    operator = "Gemm"
    template_file = "pico_cnn_fc.c"
    
    @classmethod
    def create(cls, node, graph, memory_manager):
        attrs = node.attrs
     
        if node.attrs['alpha'] != 1.0:
            return None
        if node.attrs['beta'] != 1.0:
            return None
        if node.attrs['transB'] != 1:
            return None
    
        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        weight_buffer = memory_manager.get_buffer(graph, node.inputs[1])
        bias_buffer = None
        if len(node.inputs) > 2:
            bias_buffer = memory_manager.get_buffer(graph, node.inputs[2])
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])
                
        input_size = reduce_mult(input_buffer.shape)
        output_size = reduce_mult(output_buffer.shape)

        operation = cls(node, graph)

        operation.attributes['input_buffer']  = input_buffer
        operation.attributes['input_size']  = input_size
        operation.attributes['weight_buffer'] = weight_buffer
        operation.attributes['bias_buffer']   = bias_buffer
        operation.attributes['output_buffer'] = output_buffer
        operation.attributes['output_size'] = output_size
        
        return operation

OperationRegistry.register(FullyConnected)
 
class MaxPool1D(BaseLayer):
    name = "PicoCNNMaxPool1D"
    operator = "MaxPool"
    template_file = "pico_cnn_max_pool1d.c"
    
    @classmethod
    def create(cls, node, graph, memory_manager):
        attrs=node.attrs

        assert len(attrs["kernel_shape"]) == 1
        assert tuple(attrs["pads"]) == (0, 0)

        
        input_id = node.inputs[0]
        input_shape = graph.get_shape(input_id, node)
        input_buffer = "buffer" + input_id
        input_channels = input_shape[1]

        output_buffer = "buffer" + node.outputs[0]

        if graph.is_output(node.outputs[0]):
            output_buffer = "output" + node.outputs[0]

        output_width = graph.get_shape(node.outputs[0], node)[2]
    
        kernel_size = attrs["kernel_shape"][0]
        kernel_stride = attrs["strides"][0]

        input_buffer_size = reduce_mult(input_shape)

OperationRegistry.register(MaxPool1D)
        
class Relu(BaseLayer):
    name = "PicoCNNRelu"
    operator = "Relu"
    template_file = "pico_cnn_relu.c"
    
    @classmethod
    def create(cls, node, graph, memory_manager):
        print("generating relu layer")

        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])

        input_shape = input_buffer.shape    
        input_channels = input_shape[1]
        input_height = input_shape[2]
        input_width = 1
        if len(input_shape) >= 4:
            input_width = input_shape[3]

        operation = cls(node, graph)
        
        operation.attributes['input_channels'] = input_channels
        operation.attributes['input_buffer']  = input_buffer
        operation.attributes['input_height']  = input_height
        operation.attributes['input_width']   = input_width
        operation.attributes['output_buffer'] = output_buffer

        return cls 
        
OperationRegistry.register(Relu)


class BatchNorm(BaseLayer):
    name = "PicoCNNBatchNorm"
    operator = "BatchNormalization"
    template_file = "pico_cnn_batchnorm.c"

    @classmethod
    def create(cls, node, graph, memory_manager):

        attrs = node.attrs
        
        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        mean_buffer = memory_manager.get_buffer(graph, node.inputs[1])
        variance_buffer = memory_manager.get_buffer(graph, node.inputs[2])
        bias_buffer = memory_manager.get_buffer(graph, node.inputs[3])
        
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])
        operation=cls(node,graph)
        
        input_shape = input_buffer.shape    
        input_channels = input_shape[1]
        input_height = input_shape[2]
        input_width = 1
        if len(input_shape) >= 4:
            input_width = input_shape[3]

        operation = cls(node, graph)
        operation.attributes['input_channels'] = input_channels
        operation.attributes['input_buffer']  = input_buffer
        operation.attributes['input_height']  = input_height
        operation.attributes['input_width']   = input_width
        operation.attributes['output_buffer'] = output_buffer
        operation.attributes['mean_buffer'] = mean_buffer
        operation.attributes['variance_buffer'] = variance_buffer
        operation.attributes['bias_buffer'] = bias_buffer
        operation.attributes['eps'] = attrs['epsilon']
        
        
        return operation
    
OperationRegistry.register(BatchNorm)
    

class Clip(BaseLayer):
    name = "PicoCNNClip"
    operator = "Clip"
    template_file = "pico_cnn_clip.c"
    
    @classmethod
    def create(cls, node, graph, memory_manager):
        print("generating clip layer")

        attrs = node.attrs 
        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])

        input_shape = input_buffer.shape    
        input_channels = input_shape[1]
        input_height = input_shape[2]
        input_width = 1
        if len(input_shape) >= 4:
            input_width = input_shape[3]

        operation = cls(node, graph)
        
        operation.attributes['input_channels'] = input_channels
        operation.attributes['input_buffer']  = input_buffer
        operation.attributes['input_height']  = input_height
        operation.attributes['input_width']   = input_width
        operation.attributes['output_buffer'] = output_buffer
        operation.attributes['max'] = attrs['max']
        operation.attributes['min'] = attrs['min']

        return operation

OperationRegistry.register(Clip)

class MatMul(BaseLayer):
    name = "PicoCNNMatMul"
    operator = "MatMul"
    template_file = "pico_cnn_matmul.c"

    @classmethod
    def create(cls, node, graph, memory_manager):
        attrs = node.attrs 

        
        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        weight_buffer = memory_manager.get_buffer(graph, node.inputs[1])
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])
                
        input_size = reduce_mult(input_buffer.shape)
        output_size = reduce_mult(output_buffer.shape)

        operation = cls(node, graph)

        operation.attributes['input_buffer']  = input_buffer
        operation.attributes['input_size']  = input_size
        operation.attributes['weight_buffer'] = weight_buffer
        operation.attributes['output_buffer'] = output_buffer
        operation.attributes['output_size'] = output_size
        
        return operation
    

OperationRegistry.register(MatMul)



class AveragePool(BaseLayer):
    name = "PicoCNNAveragePool"
    operator = "AveragePool"
    template_file = "pico_cnn_average_pool.c"

    @classmethod
    def create(cls, node, graph, memory_manager):
        attrs = node.attrs 
        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])
        bias_buffer = None
        
        input_shape = input_buffer.shape    
        kernel_shape = attrs["kernel_shape"]

        if not (len(kernel_shape) == 1 or (len(kernel_shape) == 2 and kernel_shape[1] == 1)):
            print("Currently only supports 1d sizes")

            return None

        kernel_size = kernel_shape[0]
        kernel_stride = attrs["strides"][0]

        if kernel_stride != 1 and kernel_stride != input_shape[2]:
            print("Currently only supports stride 1 in average pooling")
            return None
        
        operation = cls(node, graph)
        
        operation.attributes["input_buffer"] = input_buffer
        operation.attributes["input_width"] = input_buffer.shape[2]
        operation.attributes["input_channels"] = input_buffer.shape[1]
        operation.attributes["output_buffer"] = output_buffer
        operation.attributes["output_width"] = output_buffer.shape[2]
        operation.attributes["kernel_size"] = kernel_size
        operation.attributes["kernel_stride"] = kernel_stride
        operation.attributes["bias_buffer"] = bias_buffer
        
        return operation
    

OperationRegistry.register(AveragePool)




class Transpose(BaseLayer):
    name = "TransposeGeneric"
    operator = "Transpose"
    template_file = "transpose.c"

    @classmethod
    def create(cls, node, graph, memory_manager):
        attrs = node.attrs 
        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])

        input_def =  "float_t (*x)[" +"][".join((str(x) for x in input_buffer.shape[1:])) + "]";                                        
        output_def = "float_t (*y)[" +"][".join((str(x) for x in output_buffer.shape[1:])) + "]";

        input_cast = "float (*)[" + "][".join((str(x) for x in input_buffer.shape[1:])) + "]" 
        output_cast = "float (*)[" + "][".join((str(x) for x in output_buffer.shape[1:])) + "]" 

        permutations = attrs['perm']
        transpose_code = ""
        print(input_buffer.shape)
        for input_dim, output_dim in enumerate(permutations):
            dim_size = input_buffer.shape[input_dim] if input_dim < len(input_buffer.shape) else 1
            transpose_code += "  " * (input_dim+1)
            transpose_code += "for(int dim{} = 0; dim{} < {}; dim{}++)".format(input_dim, input_dim, dim_size, input_dim)
            transpose_code += "\n"

        transpose_code += "  " * len(permutations)
        transpose_code += "    " + "y[" + "][".join(("dim"+str(x) for x in permutations)) + "] = x[" +"][".join(("dim"+str(x) for x in range(len(input_buffer.shape)))) + "];"     
            
        operation = cls(node, graph)

        
        operation.attributes['input_buffer'] = input_buffer
        operation.attributes['output_buffer'] = output_buffer
        operation.attributes['input_def'] = input_def
        operation.attributes['output_def'] = output_def
        operation.attributes['input_cast'] = input_cast
        operation.attributes['output_cast'] = output_cast
        operation.attributes['transpose_code'] = transpose_code

        
        return operation
    

OperationRegistry.register(Transpose)
class Reshape(BaseLayer):
    name = "ReshapeGeneric"
    operator = "Reshape"
    template_file = "reshape.c"

    @classmethod
    def create(cls, node, graph, memory_manager):
        attrs = node.attrs 
        input_buffer = memory_manager.get_buffer(graph, node.inputs[0])
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])

        
        operation = cls(node, graph)
        operation.attributes['input_buffer'] = input_buffer
        operation.attributes['output_buffer'] = output_buffer
        return operation
    
OperationRegistry.register(Reshape)


class Add(BaseLayer):
    name = "AddGeneric"
    operator = "Add"
    template_file = "pico_cnn_add.c"

    @classmethod
    def create(cls, node, graph, memory_manager):
        attrs = node.attrs 
        input_buffers = [memory_manager.get_buffer(graph, i) for i in  node.inputs]
        output_buffer = memory_manager.get_buffer(graph, node.outputs[0])

        input_shapes = [b.shape for b in input_buffers]
        for shape in input_shapes:
            if shape != input_shapes[0]:
                print("Broadcasting is not supported for add operation")
                return None
            
        operation = cls(node, graph)
        operation.attributes["input_buffers"] = input_buffers
        operation.attributes["output_buffer"] = output_buffer
        
        return operation
    

OperationRegistry.register(Add)

class Sum(Add):
    name = "SumGeneric"
    operator = "Sum"
    template_file = "pico_cnn_add.c"

OperationRegistry.register(Sum)

    
