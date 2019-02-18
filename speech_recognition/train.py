from collections import ChainMap
from .config import ConfigBuilder
import argparse
import os
import random
import sys
import json

from torch.autograd import Variable
import numpy as np
import torch
import torch.nn as nn
import torch.utils.data as data
import itertools

from tensorboardX import SummaryWriter

from . import models as mod
from . import dataset

sys.path.append(os.path.join(os.path.dirname(__file__), "distiller"))

import distiller
from distiller.data_loggers import TensorBoardLogger, PythonLogger
import apputils

def get_eval(scores, labels, loss):
    batch_size = labels.size(0)
    accuracy = (torch.max(scores, 1)[1].view(batch_size).data == labels.data).float().sum() / batch_size
    loss = loss.item()

    return accuracy.item(), loss

def print_eval(name, scores, labels, loss, end="\n", logger=None):
    accuracy, loss = get_eval(scores, labels, loss) 
    if logger:
        logger.info("{} accuracy: {:>5}, loss: {:<25}".format(name, accuracy, loss))
    else:
        print("{} accuracy: {:>5}, loss: {:<25}".format(name, accuracy, loss), end=end)
    return accuracy, loss


def set_seed(config):
    seed = config["seed"]
    torch.manual_seed(seed)
    np.random.seed(seed)
    if not config["no_cuda"]:
        torch.cuda.manual_seed(seed)
    random.seed(seed)

def evaluate(model_name, config, model=None, test_loader=None, logfile=None):
    print("Evaluating network")
    
    if not test_loader:
        _, _, test_set = dataset.SpeechDataset.splits(config)
        test_loader = data.DataLoader(test_set, batch_size=1)
    if not config["no_cuda"]:
        torch.cuda.set_device(config["gpu_no"])
    if not model:
        model = config["model_class"](config)
        model.load(config["input_file"])
    if not config["no_cuda"]:
        torch.cuda.set_device(config["gpu_no"])
        model.cuda()
    model.eval()
    criterion = nn.CrossEntropyLoss()
    accs = []
    losses = []
    for model_in, labels in test_loader:
        model_in = Variable(model_in, requires_grad=False)
        if not config["no_cuda"]:
            model_in = model_in.cuda()
            labels = labels.cuda()
        
        scores = model(model_in)
        labels = Variable(labels, requires_grad=False)
        loss = criterion(scores, labels)
        acc, loss = get_eval(scores, labels, loss)
        accs.append(acc)
        losses.append(loss)
        
    print("final test accuracy: {}, loss: {}".format(np.mean(accs), np.mean(losses)))
    return np.mean(accs), np.mean(losses)

def train(model_name, config):
    output_dir = os.path.join(config["output_dir"], model_name)
    print("All information will be saved to: ", output_dir)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    train_log = open(os.path.join(output_dir, "train.csv"), "w")
    
    with SummaryWriter() as summary_writer:
        train_set, dev_set, test_set = dataset.SpeechDataset.splits(config)

        config["width"] = train_set.width
        config["height"] = train_set.height

        with open(os.path.join(output_dir, 'config.json'), "w") as o:
                  s = json.dumps(dict(config), default=lambda x: str(x), indent=4, sort_keys=True)
                  o.write(s)

        # Setip optimizers
        model = config["model_class"](config)
        if config["input_file"]:
            model.load(config["input_file"])
        if not config["no_cuda"]:
            torch.cuda.set_device(config["gpu_no"])
            model.cuda()
        optimizer = torch.optim.SGD(model.parameters(), 
                                    lr=config["lr"], 
                                    nesterov=config["use_nesterov"],
                                    weight_decay=config["weight_decay"], 
                                    momentum=config["momentum"])
        sched_idx = 0
        criterion = nn.CrossEntropyLoss()
        max_acc = 0

        n_epochs = config["n_epochs"]
        
        # Setup learning rate optimizer
        lr_scheduler = config["lr_scheduler"]
        scheduler = None
        if lr_scheduler == "step":
            gamma = config["lr_gamma"]
            stepsize = config["lr_stepsize"]
            if stepsize == 0:
                stepsize = max(10, n_epochs // 5)
            
            scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=stepsize, gamma=gamma)
            
        elif lr_scheduler == "multistep":
            gamma = config["lr_gamma"]
            steps = config["lr_steps"]
            if steps == [0]:
                steps = itertools.count(max(1, n_epochs//10), max(1, n_epochs//10))

            scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer,
                                                             steps,
                                                             gamma=gamma)
                
        elif lr_scheduler == "exponential":
            gamma = config["lr_gamma"]
            scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma)  
        elif lr_scheduler == "plateau":
            gamma = config["lr_gamma"]
            patience = config["lr_patience"]
            scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer,
                                                                   mode='min',
                                                                   factor=gamma,
                                                                   patience=patience,
                                                                   threshold=0.0001,
                                                                   threshold_mode='rel',
                                                                   cooldown=0,
                                                                   min_lr=0,
                                                                   eps=1e-08)

        else:
            raise Exception("Unknown learing rate scheduler: {}".format(lr_scheduler))
        
        # setup datasets
        
        train_loader = data.DataLoader(train_set, batch_size=config["batch_size"], shuffle=True, drop_last=True)
        dev_loader = data.DataLoader(dev_set, batch_size=min(len(dev_set), 16), shuffle=True)
        test_loader = data.DataLoader(test_set, batch_size=1, shuffle=True)


        # Setup distiller for model minimization
        msglogger = apputils.config_pylogger('logging.conf', None, os.path.join(output_dir, "logs"))
        tflogger = TensorBoardLogger(msglogger.logdir)
        tflogger.log_gradients = True
        pylogger = PythonLogger(msglogger)

        compression_scheduler = None
        if config["compress"]:
            print("Activating compression scheduler")


            compression_scheduler = distiller.file_config(model, optimizer, config["compress"])
            if not config["no_cuda"]:
                model.cuda()

        # Export model
        dummy_input, dummy_label = next(iter(test_loader))
        if not config["no_cuda"]:
            dummy_input = dummy_input.cuda()
       
        model.eval()
        summary_writer.add_graph(model, dummy_input)

        # iteration counters 
        step_no = 0

        for epoch_idx in range(n_epochs):
            msglogger.info("Training epoch", epoch_idx, "of", config["n_epochs"])
            if compression_scheduler is not None:
                compression_scheduler.on_epoch_begin(epoch_idx)
            
            for batch_idx, (model_in, labels) in enumerate(train_loader):
                model.train()
                if compression_scheduler is not None:
                    compression_scheduler.on_minibatch_begin(epoch_idx, batch_idx, len(train_loader))
                    
                optimizer.zero_grad()
                if not config["no_cuda"]:
                    model_in = model_in.cuda()
                    labels = labels.cuda()
                model_in = Variable(model_in, requires_grad=False)
                scores = model(model_in)
                labels = Variable(labels, requires_grad=False)
                loss = criterion(scores, labels)

                if compression_scheduler is not None:
                    compression_scheduler.before_backward_pass(epoch_idx, batch_idx, len(train_loader), loss)
                loss.backward()
                optimizer.step()
                if compression_scheduler is not None:
                    compression_scheduler.on_minibatch_end(epoch_idx, batch_idx, len(train_loader))

                step_no += 1

                scalar_accuracy, scalar_loss = get_eval(scores, labels, loss)

                summary_writer.add_scalars('training', {'accuracy': scalar_accuracy,
                                                        'loss': scalar_loss},
                                           step_no)
                train_log.write("train,"+str(step_no)+","+str(scalar_accuracy)+","+str(scalar_loss)+"\n")
                
                print_eval("train step #{}".format(step_no), scores, labels, loss, logger=msglogger)

                
                #for module in model.children():
                #    print(module)
                #    for parameter in module.parameters():
                #        print(parameter)
                        

            # Validate
            model.eval()
            accs = []
            losses = []
            for model_in, labels in dev_loader:
                model_in = Variable(model_in, requires_grad=False)
                if not config["no_cuda"]:
                    model_in = model_in.cuda()
                    labels = labels.cuda()
                scores = model(model_in)
                labels = Variable(labels, requires_grad=False)
                loss = criterion(scores, labels)
                loss_numeric = loss.item()
                acc, loss = get_eval(scores, labels, loss)
                accs.append(acc)
                losses.append(loss)
            
            avg_acc = np.mean(accs)
            avg_loss = np.mean(losses) 
            msglogger.info("validation accuracy: {}, loss: {}".format(avg_acc, avg_loss))
            train_log.write("val,"+str(step_no)+","+str(avg_acc)+","+str(avg_loss)+"\n")

            summary_writer.add_scalars('validation', {'accuracy': avg_acc,
                                                      'loss': avg_loss},
                                       step_no)
            
            if avg_acc > max_acc:
                msglogger.info("saving best model...")
                max_acc = avg_acc
                model.save(os.path.join(output_dir, "model.pt"))


                msglogger.info("saving onnx...")
                try:
                    model_in, label = next(iter(test_loader), (None, None))
                    if not config["no_cuda"]:
                        model_in = model_in.cuda()
                    model.save_onnx(os.path.join(output_dir, "model.onnx"), model_in)
                except Exception as e:
                    msglogger.error("Could not export onnx model ...\n {}".format(str(e)))
                    
            if scheduler is not None:
                if type(lr_scheduler) == torch.optim.lr_scheduler.ReduceLROnPlateau:
                    scheduler.step(avg_loss)
                else:
                    scheduler.step()
                    
            if compression_scheduler is not None:
                compression_scheduler.on_epoch_begin(epoch_idx)
                
        model.load(os.path.join(output_dir, "model.pt"))
        test_accuracy = evaluate(model_name, config, model, test_loader)
        train_log.write("test,"+str(step_no)+","+str(test_accuracy)+"\n")
        train_log.close()
        
def main():
    output_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "trained_models")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=[x.value for x in list(mod.ConfigType)], default="ekut-raw-cnn3", type=str)
    config, _ = parser.parse_known_args()

    model_name = config.model
    
    global_config = dict(no_cuda=False, n_epochs=500,
                         lr=0.1, lr_scheduler="step", lr_gamma=0.1,
                         lr_stepsize = 0, lr_steps = [0], lr_patience = 10, 
                         batch_size=64, seed=0, use_nesterov=False,
                         input_file="", output_dir=output_dir, gpu_no=0,
                         compress="", 
                         cache_size=32768, momentum=0.9, weight_decay=0.00001)
    
    mod_cls = mod.find_model(config.model)
    builder = ConfigBuilder(
        mod.find_config(config.model),
        dataset.SpeechDataset.default_config(),
        global_config)
    parser = builder.build_argparse()
    parser.add_argument("--type", choices=["train", "eval"], default="train", type=str)
    config = builder.config_from_argparse(parser)
    config["model_class"] = mod_cls
    set_seed(config)
    if config["type"] == "train":
        train(model_name, config)
    elif config["type"] == "eval":
        evaluate(model_name, config)

if __name__ == "__main__":
    main()
