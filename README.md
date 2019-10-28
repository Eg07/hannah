# Deep Neural Networks for Speech Recognition

# Getting Started 


## Installing dependencies

Dependencies can either be installed to your Home-Directory or to a seperate python virtual environment.
On RedHat 7 based distros (Scientific Linux 7, CentOS 7) all required dependencies should be installed by bootstrap.sh 

On other distros we need the following packages:

- python3.6 and development headers
- portaudio and development headers
- freeglut and development headers

On Ubuntu 16.04 these are installable with the following commands:

    sudo apt-get update
    sudo apt-get -y install software-properties-common python-software-properties
    sudo add-apt-repository -y ppa:jonathonf/python-3.6
    sudo apt-get update
    
    sudo apt-get -y install python3.6-dev freeglut3-dev portaudio19-dev
    sudo apt-get -y install git curl wget
    curl https://bootstrap.pypa.io/get-pip.py | sudo python3.6


### Setup of virtual environment (recommended)

To install in a python virtual environment use for training on cpus:

    ./bootstrap.sh --venv
    
or for training on gpus:

    ./bootstrap.sh --venv --gpu

or for training on cluster-gpu0x:

    ./bootstrap.sh --gpu_cluster
    
*Audioread 2.1.8 increases training time dramatically. Version 2.1.6 is recommended.*

And activate the venv using:

    source venv/bin/activate

Export LD\_LIBRARY\_PATH when training on cluster-gpu0x:

    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/graphics/opt/opt_Ubuntu18.04/cuda/toolkit_9.0/cuda/lib64/:/graphics/opt/opt_Ubuntu18.04/cuda/cudnn/7.1.4_for_9.0/cuda/lib64

### Setup with installation to home directory

Dependencies can be installed by invoking:

    ./bootstrap.sh
	
For training on GPUs use:

    ./bootstrap.sh --gpu
    
	
## Installing the datasets
	
Installing dataset for KWS:

    cd datasets
	./get_datasets.sh
	
Installing dataset for VAD:

    cd datasets
    ./get_datasets_vad.sh

## Training - KWS

Training on CPU can be invoked by:
   
    python3.6 -m speech_recognition.train  --no_cuda  --model ekut-raw-cnn3-relu

Training on 1st GPU can be invoked by:

    python3.6 -m speech_recognition.train  --gpu_no 0  --model ekut-raw-cnn3-relu

Trained models are saved under trained_models/model_name .

## Evaluation

To run only the evalution of a model use:

    python3.6 -m speech_recognition.train --no_cuda 0 --model ekut-raw-cnn3-relu --batch_size 256 --input_file trained_models/ekut-raw-cnn3-relu/model.pt --type eval

## Training - VAD

Training for the simple-vad, bottleneck-vad and small-vad can be invoked by:

    python3 -m speech_recognition.train --model simple-vad      --dataset vad --data_folder datasets/vad_data_balanced --n-labels 2 --lr 0.001 --silence_prob 0 --early_stopping 3 --input_length 6360 --stride 2 --conv1_size 5 --conv1_features 40 --conv2_size 5 --conv2_features 20 --conv3_size 5 --conv3_features 10 --fc_size 40
    python3 -m speech_recognition.train --model bottleneck-vad  --dataset vad --data_folder datasets/vad_data_balanced --n-labels 2 --lr 0.001 --n-mfcc 40 --silence_prob 0 --early_stopping 3 --input_length 6360 --stride 2 --conv1_size 5 --conv1_features 40 --conv2_size 5 --conv2_features 20 --conv3_size 5 --conv3_features 10 --fc_size 250
    python3 -m speech_recognition.train --model small-vad       --dataset vad --data_folder datasets/vad_data_balanced --n-labels 2
    
# Exporting Models for RISC-V
	
The export is currently not available. 


# TODO:
Training:
  
- Implement Wavenet
- Experiment with dilations
- Add design space exploration tool (WIP)
- Add estimation of non functional properties on algorithmic level (WIP)

Export ISA / RT-Level:
- Make usable again
- Use relay IR / TVM
- 2D Convolutions
- Average Pooling
- Dilations
- Depthwise separable convolutions
- Batch normalization
- Add Memory Allocator
- Add Quantization support
