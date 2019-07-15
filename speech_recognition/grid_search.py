"""
 This is first version of a grid search.
 Right now it has many limitations:
    - designed for lucille:
        - 4 gpus with 16gb ram
    - number of gpus is not considered
    - not all hyperparameters are considered
    - no summary is generated
    - no visualization 
"""


from .train import build_config
import itertools

def main():
    model_name, config = build_config()
    n_epochs = 1
    num_gpu = 4

 #   print('Model name: ', model_name, ' Config: ', config)

    with open('grid_search.sh', mode='w+') as f:
        print('#!/bin/bash', file=f)
        for num_feature in range(10,40,10):
            for feature, gpu in {('mfcc', 0), ('mel', 1), ('spectrogram', 2), ('melspec', 3)}:
                for bottleneck in tuple(itertools.product(range(2), range(2))):
                    for separable in tuple(itertools.product(range(2), range(2))):
                        id='feature' + feature + 'numFeature' + str(num_feature) + 'bottle' + str(bottleneck[0]) + str(bottleneck[1]) + 'separable' + str(separable[0]) + str(separable[1])
                        bottleneck_str = str(bottleneck).translate(str.maketrans("", "", ",()"))
                        separable_str = str(separable).translate(str.maketrans("", "", ",()"))

                        print('python3.6 -m speech_recognition.train '
                              '--n_epochs {} '
                              '--early-stopping 10 '
                              '--model {} '
                              '--experiment-id {} '
                              '--feature {} '
                              '--gpu_no {} '
                              '--n_mels {} '
                              '--n_mfcc {} '
                              '--bottleneck {} '
                              '--separable {} '
                              ' > /dev/null 2>&1 &'
                              .format(n_epochs, model_name, id, feature, gpu, num_feature, num_feature, bottleneck_str, separable_str), file=f)
                        print('', file=f)
            # Process multiple trainings per GPU at the same time
            print('wait', file=f)

if __name__ == "__main__":
    main()