FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3 python3-venv python3-pip mininet openvswitch-switch \
    iproute2 iputils-ping net-tools procps ca-certificates kmod \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /project
COPY requirements-sdn.txt /tmp/requirements-sdn.txt
RUN python3 -m venv --system-site-packages /opt/sdn \
    && /opt/sdn/bin/python -m pip install --no-cache-dir --timeout 120 -r /tmp/requirements-sdn.txt
RUN apt-get update && apt-get install -y --no-install-recommends python3-matplotlib \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends ethtool \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/sdn/bin:${PATH}"
COPY . /project
RUN make -C src
ENTRYPOINT ["sh", "/project/scripts/container_entrypoint.sh"]
CMD ["python", "scripts/run_experiments.py", "--datapath", "user"]
