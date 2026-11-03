"""Choose branches eligible for DSCP DATA rules using the routing policy."""


def eligible_paths(policy, selected):
    # Static experiments must retain their intentionally fixed route.
    if policy.mode != "failover" or selected is None:
        return frozenset()
    paths = {selected} if policy.available(selected) else set()
    selected_score = policy.health.get(selected)
    if selected_score is not None:
        for path in ("upper", "lower"):
            score = policy.health.get(path)
            if (policy.available(path) and score is not None
                    and score <= selected_score + .02):
                paths.add(path)
    return frozenset(paths)
