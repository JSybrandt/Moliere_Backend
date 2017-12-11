#!/bin/bash
mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 fs-6ca3fe25.efs.us-east-1.amazonaws.com:/ /efs
# Identify the project home dir
PROJ_HOME=/efs/moliere

# Get Shortest Path
GRAPH=$PROJ_HOME/data/final.bin.edges
LABELS=$PROJ_HOME/data/final.labels
WORD_VEC=$PROJ_HOME/data/canon.vec
PMID_VEC=$PROJ_HOME/data/centroids.data
UMLS_VEC=$PROJ_HOME/data/umls.data
SOURCE_IDX=$( grep -nwm1 $SOURCE_WORD $LABELS | awk 'BEGIN{FS=":"}{print $1-1}')
TARGET_IDX=$( grep -nwm1 $TARGET_WORD $LABELS | awk 'BEGIN{FS=":"}{print $1-1}')
OUT="/efs/out_shortest.txt"

$PROJ_HOME/code/findPath/bin/./findPath -g $GRAPH \
           -l $LABELS \
           -s $SOURCE_IDX \
           -t $TARGET_IDX \
           -V $WORD_VEC \
           -P $PMID_VEC \
           -U $UMLS_VEC \
           -e 1.5 \
           -o $OUT

# Get Abstract Cloud
PATHS=$OUT
OUT="/efs/out_abstract.txt"
$PROJ_HOME/code/paths2dijk/bin/paths2Dijk -g $GRAPH -l $LABELS -p $PATHS -o $OUT

# Create Sub Corpus
CLOUD=$OUT
mkdir /efs/subcorpusresults
OUT="/efs/subcorpusresults"
ABSTRACT=$PROJ_HOME/data/abstracts.txt
python3 $PROJ_HOME/code/dijk2BoWCorpus/dijk2Data.py -l $LABELS -p $CLOUD -o $OUT -a $ABSTRACT

# Create Topic Model
IN="$OUT/$TARGET_WORD---$SOURCE_WORD"
OUT="/efs/moliere/$TARGET_WORD---$SOURCE_WORD---results"
VIEW="/efs/moliere/results.txt"
mpiexec --allow-run-as-root /efs/moliere/tools/mpi_lda  --num_topics 2 \
                         --alpha 1 \
                         --beta 0.01 \
                         --training_data_file $IN \
                         --model_file $OUT \
                         --total_iterations 500 \
                         --burn_in_iterations 50 \
python $PROJ_HOME/tools/view_model.py ${OUT} ${VIEW}
python $PROJ_HOME/tools/txttojson.py $VIEW /efs/moliere/results_json.txt
aws s3 cp /efs/moliere/results_json.txt s3://results-moliere/CSV_Results/
aws s3 cp $VIEW s3://results-moliere/Compute_Results/
