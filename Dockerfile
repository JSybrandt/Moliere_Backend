FROM ubuntu:latest
RUN apt-get update
RUN apt-get install nfs-common -y
RUN apt-get install python-pip -y
RUN apt-get install unzip -y
RUN apt-get install sqlite -y
RUN apt-get install openmpi-bin -y
RUN apt-get install python3 -y
RUN apt-get install mpich -y
RUN pip install awscli
RUN mkdir /efs
ADD fetch_and_run.sh /usr/local/bin/fetch_and_run.sh
WORKDIR /tmp
USER nobody
ENTRYPOINT ["/usr/local/bin/fetch_and_run.sh"]
