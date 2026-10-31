"""Apply impairments through Mininet's managed TC interfaces."""


def set_link_state(network, first="s1", second="s2", state="down"):
    if state not in ("up", "down"):
        raise ValueError("link state must be up or down")
    network.configLinkStatus(first, second, state)


def set_link_loss(network, first, second, loss):
    if not 0 <= loss <= 100:
        raise ValueError("loss must be in 0..100")
    links = network.linksBetween(network.get(first), network.get(second))
    if len(links) != 1:
        raise ValueError("expected exactly one link between the named nodes")
    # Preserve bandwidth/delay when changing loss. TCIntf.config reconstructs
    # the interface's qdisc and must receive the other existing parameters.
    for interface in (links[0].intf1, links[0].intf2):
        options = dict(interface.params)
        options["loss"] = loss
        result = interface.config(**options)
        if result and any(result.get("tcoutputs", [])):
            raise RuntimeError("Traffic-control configuration failed on " + interface.name)


def set_host_reordering(network, percent=20):
    """Host links have no bandwidth qdisc; branch HTB/netem stays intact."""
    if not 0 <= percent <= 100:
        raise ValueError("reorder percentage must be in 0..100")
    for host in network.hosts:
        result = host.cmd("tc qdisc replace dev %s root netem delay 8ms 2ms reorder %s%% 50%%" %
                          (host.defaultIntf(), percent))
        if result.strip():
            raise RuntimeError("Host reordering setup failed: " + result)
