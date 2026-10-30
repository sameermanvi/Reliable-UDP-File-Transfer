FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3 python3-venv python3-pip mininet openvswitch-switch \
    iproute2 iputils-ping net-tools procps ca-certificates ethtool \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /project
COPY requirements-sdn.txt /tmp/requirements-sdn.txt
RUN python3 -m venv --system-site-packages /opt/sdn \
    && /opt/sdn/bin/pip install --no-cache-dir -r /tmp/requirements-sdn.txt
ENV PATH="/opt/sdn/bin:${PATH}"
COPY . /project
RUN make -C src clean all
ENTRYPOINT ["sh", "/project/scripts/container_entrypoint.sh"]
CMD ["python", "scripts/demo.py"]
