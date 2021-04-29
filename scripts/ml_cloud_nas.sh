#!/bin/bash

####
#a) Define slurm job parameters
####

#SBATCH --job-name=ml_cloud_train

#resources:

#SBATCH --cpus-per-task=20

#SBATCH --partition=gpu-2080ti-preemptable
# the slurm partition the job is queued to.

#SBATCH --nodes=1
# requests that the cores are all on one node

#SBATCH --mem=64G
# the job will need 12GB of memory equally distributed on 4 cpus.

#SBATCH --gres=gpu:rtx2080ti:5
#the job can use and see 5 GPUs (8 GPUs are available in total on one node)

#SBATCH --gres-flags=enforce-binding

#SBATCH --time=4320
# the maximum time the scripts needs to run (5 minutes)

#SBATCH --error=job_%j.err
# write the error output to job.*jobID*.err

#TSBATCH --output/home/bringmann/cgerum05/job_%j.out
#SBATCH --output=job_%j.out
# write the standard output to your home directory job.*jobID*.out

#SBATCH --mail-type=ALL
#write a mail if a job begins, ends, fails, gets requeued or stages out

#SBATCH --mail-user=christoph.gerum@uni-tuebingen.de
# your mail address


#Script
echo "Job information"
scontrol show job $SLURM_JOB_ID

#echo "Copy training data"

#cd $tcml_wd
#mkdir -p /scratch/$SLURM_JOB_ID/$tcml_output_dir
#mkdir -p /scratch/$SLURM_JOB_ID/$tcml_data_dir


echo "Moving datasets to local scratch ${SCRATCH} ${SLURM_JOB_ID}"
#ls $SCRATCH
cp -r datasets $SCRATCH
#ls $SCRATCH

cp /home/bringmann/cgerum05/ml_cloud.simg $SCRATCH

echo "Running training"
singularity run --nv  --bind $PWD:/opt/speech_recognition,$SCRATCH:/mnt $SCRATCH/ml_cloud.simg --config-name=config_unas dataset.data_folder=/mnt/datasets module.num_workers=4 experiment_id=nas3 hydra/launcher=joblib trainer.max_epochs=30  -m 

echo DONE!
